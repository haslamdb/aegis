"""
Real-time prophylaxis monitoring service.

Wires together HL7 listener, location tracker, schedule monitor,
pre-op checker, escalation engine, and state manager.

Adapted from surgical-prophylaxis/src/realtime/service.py.
"""

import asyncio
import logging
import signal
from typing import Optional

from django.utils import timezone

from apps.surgical_prophylaxis.fhir_client import FHIRClient
from apps.surgical_prophylaxis.logic.config import Config
from apps.surgical_prophylaxis.logic.hl7.listener import HL7MLLPServer, HL7ListenerConfig, MessageHandler
from apps.surgical_prophylaxis.logic.hl7.location_tracker import LocationTracker, PatientLocationUpdate
from apps.surgical_prophylaxis.logic.hl7.parser import HL7Message
from apps.surgical_prophylaxis.models import AlertTrigger, SurgicalJourney

from .escalation_engine import EscalationEngine
from .preop_checker import PreOpChecker
from .schedule_monitor import ScheduleMonitor
from .state_manager import StateManager

logger = logging.getLogger(__name__)


class RealtimeProphylaxisService:
    """Main real-time monitoring orchestrator."""

    def __init__(self):
        self.config = Config()
        self.fhir_client = FHIRClient()
        self.state_manager = StateManager()
        self.location_tracker = LocationTracker()
        self.preop_checker = PreOpChecker(fhir_client=self.fhir_client)
        self.schedule_monitor = ScheduleMonitor(fhir_client=self.fhir_client)
        self.escalation_engine = EscalationEngine()
        self.hl7_server: Optional[HL7MLLPServer] = None

        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Wire up callbacks
        self.location_tracker.on_pre_op_arrival = self._handle_preop_arrival
        self.location_tracker.on_or_entry = self._handle_or_entry
        self.location_tracker.on_pacu_arrival = self._handle_pacu_arrival
        self.location_tracker.on_discharge = self._handle_discharge

    async def start(self):
        """Start the real-time monitoring service."""
        logger.info("Starting real-time prophylaxis monitoring service")
        self._running = True

        # Start HL7 listener if enabled
        if self.config.HL7_ENABLED:
            handler = MessageHandler()
            handler.on_adt = self._handle_adt_message
            handler.on_orm = self._handle_scheduling_message
            handler.on_siu = self._handle_scheduling_message

            config = HL7ListenerConfig(
                host=self.config.HL7_HOST,
                port=self.config.HL7_PORT,
                enabled=True,
            )
            self.hl7_server = HL7MLLPServer(handler=handler, config=config)
            await self.hl7_server.start()

        # Start background loops
        self._tasks.append(asyncio.create_task(self._schedule_poll_loop()))
        self._tasks.append(asyncio.create_task(self._scheduled_check_loop()))
        self._tasks.append(asyncio.create_task(self._escalation_loop()))

        logger.info("Real-time service started")

    async def stop(self):
        """Stop the service gracefully."""
        logger.info("Stopping real-time prophylaxis monitoring service")
        self._running = False

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self.hl7_server:
            await self.hl7_server.stop()

        logger.info("Real-time service stopped")

    async def run(self):
        """Run until interrupted."""
        await self.start()

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        # Keep running
        while self._running:
            await asyncio.sleep(1)

    async def _handle_adt_message(self, message: HL7Message):
        """Handle ADT (patient movement) messages."""
        update = await self.location_tracker.process_adt(message)
        if update:
            # Find or create journey for this patient
            journey = self.state_manager.get_journey_for_patient(update.patient_mrn)
            if journey:
                self.state_manager.update_location(
                    journey.journey_id,
                    update.new_location_code,
                    update.new_location_state,
                    event_time=update.event_time,
                    hl7_message_id=update.message_control_id or '',
                )

    async def _handle_scheduling_message(self, message: HL7Message):
        """Handle ORM/SIU (scheduling) messages."""
        # Process via schedule monitor
        logger.debug(f"Received scheduling message: {message.message_type}^{message.message_event}")

    async def _handle_preop_arrival(self, update: PatientLocationUpdate):
        """Patient arrived in pre-op holding."""
        journey = self.state_manager.get_journey_for_patient(update.patient_mrn)
        if not journey:
            return

        result = self.preop_checker.check_on_preop_arrival(journey)
        self.state_manager.record_check(journey, result)

        if result['alert_required']:
            self.escalation_engine.send_alert(
                journey, AlertTrigger.PREOP_ARRIVAL,
                result['alert_severity'], result['recommendation'],
            )

    async def _handle_or_entry(self, update: PatientLocationUpdate):
        """Patient entered OR — most critical moment."""
        journey = self.state_manager.get_journey_for_patient(update.patient_mrn)
        if not journey:
            return

        result = self.preop_checker.check_on_or_entry(journey)
        self.state_manager.record_check(journey, result)

        if result['alert_required']:
            self.escalation_engine.send_alert(
                journey, AlertTrigger.OR_ENTRY,
                result['alert_severity'], result['recommendation'],
            )

    async def _handle_pacu_arrival(self, update: PatientLocationUpdate):
        """Patient arrived in PACU — surgery complete."""
        logger.info(f"Patient {update.patient_mrn} arrived in PACU")

    async def _handle_discharge(self, update: PatientLocationUpdate):
        """Patient discharged from surgical pathway."""
        journey = self.state_manager.get_journey_for_patient(update.patient_mrn)
        if journey:
            self.state_manager.complete_journey(journey.journey_id)
            self.location_tracker.clear_patient(update.patient_mrn)

    async def _schedule_poll_loop(self):
        """Periodically poll FHIR for new scheduled surgeries."""
        interval = self.config.FHIR_SCHEDULE_POLL_INTERVAL * 60
        while self._running:
            try:
                await self.schedule_monitor.poll_fhir_schedule(
                    lookahead_hours=self.config.FHIR_LOOKAHEAD_HOURS,
                )
            except Exception as e:
                logger.error(f"Error in schedule poll: {e}")
            await asyncio.sleep(interval)

    async def _scheduled_check_loop(self):
        """Check scheduled surgeries for trigger windows every 60 seconds."""
        while self._running:
            try:
                alerts_needed = self.schedule_monitor.get_surgeries_needing_alerts()
                for trigger, surgeries in alerts_needed.items():
                    for surgery in surgeries:
                        journey = self.state_manager.get_journey_for_patient(surgery.patient_mrn)
                        if journey and not getattr(journey, f'alert_{trigger}_sent', False):
                            result = self.preop_checker.check_at_trigger(journey, trigger)
                            self.state_manager.record_check(journey, result)
                            if result['alert_required']:
                                self.escalation_engine.send_alert(
                                    journey, trigger,
                                    result['alert_severity'], result['recommendation'],
                                )
                                self.state_manager.mark_alert_sent(journey.journey_id, trigger)
            except Exception as e:
                logger.error(f"Error in scheduled check loop: {e}")
            await asyncio.sleep(60)

    async def _escalation_loop(self):
        """Check for overdue escalations every 30 seconds."""
        while self._running:
            try:
                self.escalation_engine.check_escalations()
            except Exception as e:
                logger.error(f"Error in escalation loop: {e}")
            await asyncio.sleep(30)

    def get_status(self) -> dict:
        """Get service status."""
        return {
            'running': self._running,
            'hl7_enabled': self.config.HL7_ENABLED,
            'hl7_stats': self.hl7_server.get_stats() if self.hl7_server else None,
            'active_journeys': self.state_manager.get_active_journeys().count(),
            'tracked_patients': len(self.location_tracker.tracked_patients),
            'scheduled_surgeries': self.schedule_monitor.surgery_count,
        }
