"""Antibiotic Usage (AU) data extraction for NHSN reporting.

Calculates Days of Therapy (DOT) and Defined Daily Doses (DDD)
from Clarity MAR data. Saves results to Django ORM models.
"""

import logging
from datetime import date
from typing import Any

from ..models import AUMonthlySummary, AUAntimicrobialUsage, AUPatientLevel
from . import config as cfg

logger = logging.getLogger(__name__)


class AUDataExtractor:
    """Extract antibiotic usage data from Clarity for NHSN reporting."""

    def __init__(self, connection_string: str | None = None):
        self.connection_string = connection_string or cfg.get_clarity_connection_string()
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            if not self.connection_string:
                raise ValueError(
                    "No Clarity connection configured. Set CLARITY_CONNECTION_STRING "
                    "or MOCK_CLARITY_DB_PATH in environment."
                )
            from sqlalchemy import create_engine
            self._engine = create_engine(self.connection_string)
        return self._engine

    def _is_sqlite(self) -> bool:
        return 'sqlite' in (self.connection_string or '').lower()

    def get_antimicrobial_administrations(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        include_oral: bool | None = None,
    ):
        """Get raw antimicrobial administration records from Clarity."""
        import pandas as pd
        from sqlalchemy import text

        if start_date is None:
            start_date = date.today().replace(day=1)
        if end_date is None:
            end_date = date.today()
        if include_oral is None:
            include_oral = cfg.get_au_include_oral()

        location_filter = ""
        if locations:
            location_list = ", ".join(f"'{loc}'" for loc in locations)
            location_filter = f"AND loc.NHSN_LOCATION_CODE IN ({location_list})"

        route_filter = ""
        if not include_oral:
            route_filter = "AND om.ADMIN_ROUTE NOT IN ('PO', 'ORAL')"

        if self._is_sqlite():
            date_expr = "date(mar.TAKEN_TIME)"
            month_expr = "strftime('%Y-%m', mar.TAKEN_TIME)"
        else:
            date_expr = "CONVERT(DATE, mar.TAKEN_TIME)"
            month_expr = "FORMAT(mar.TAKEN_TIME, 'yyyy-MM')"

        query = f"""
        SELECT
            pat.PAT_MRN_ID as patient_id,
            pe.PAT_ENC_CSN_ID as encounter_id,
            loc.NHSN_LOCATION_CODE,
            rx.GENERIC_NAME as medication_name,
            nm.NHSN_CODE,
            nm.NHSN_CATEGORY,
            nm.DDD as ddd_value,
            nm.DDD_UNIT as ddd_unit,
            om.ADMIN_ROUTE as route,
            mar.TAKEN_TIME as admin_time,
            {date_expr} as admin_date,
            {month_expr} as month,
            mar.DOSE_GIVEN,
            mar.DOSE_UNIT,
            mar.ACTION_NAME
        FROM MAR_ADMIN_INFO mar
        JOIN ORDER_MED om ON mar.ORDER_MED_ID = om.ORDER_MED_ID
        JOIN RX_MED_ONE rx ON om.MEDICATION_ID = rx.MEDICATION_ID
        JOIN NHSN_ANTIMICROBIAL_MAP nm ON rx.MEDICATION_ID = nm.MEDICATION_ID
        JOIN PAT_ENC pe ON om.PAT_ENC_CSN_ID = pe.PAT_ENC_CSN_ID
        JOIN PATIENT pat ON pe.PAT_ID = pat.PAT_ID
        JOIN NHSN_LOCATION_MAP loc ON pe.DEPARTMENT_ID = loc.EPIC_DEPT_ID
        WHERE mar.ACTION_NAME = 'Given'
            AND mar.TAKEN_TIME >= :start_date
            AND mar.TAKEN_TIME <= :end_date
            {location_filter}
            {route_filter}
        ORDER BY pat.PAT_MRN_ID, mar.TAKEN_TIME
        """

        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                df = pd.read_sql(
                    text(query), conn,
                    params={'start_date': start_date, 'end_date': end_date},
                )
                df.columns = df.columns.str.lower()
                return df
        except Exception as e:
            logger.error(f"Antimicrobial administration query failed: {e}")
            return pd.DataFrame()

    def calculate_dot(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        include_oral: bool | None = None,
    ):
        """Calculate Days of Therapy (DOT) by location, month, and antimicrobial."""
        import pandas as pd
        from sqlalchemy import text

        if start_date is None:
            start_date = date.today().replace(day=1)
        if end_date is None:
            end_date = date.today()
        if include_oral is None:
            include_oral = cfg.get_au_include_oral()

        location_filter = ""
        if locations:
            location_list = ", ".join(f"'{loc}'" for loc in locations)
            location_filter = f"AND loc.NHSN_LOCATION_CODE IN ({location_list})"

        route_filter = ""
        if not include_oral:
            route_filter = "AND om.ADMIN_ROUTE NOT IN ('PO', 'ORAL')"

        if self._is_sqlite():
            date_expr = "date(mar.TAKEN_TIME)"
            month_expr = "strftime('%Y-%m', mar.TAKEN_TIME)"
        else:
            date_expr = "CONVERT(DATE, mar.TAKEN_TIME)"
            month_expr = "FORMAT(mar.TAKEN_TIME, 'yyyy-MM')"

        query = f"""
        SELECT
            loc.NHSN_LOCATION_CODE as nhsn_location_code,
            {month_expr} as month,
            nm.NHSN_CODE as nhsn_code,
            nm.NHSN_CATEGORY as nhsn_category,
            rx.GENERIC_NAME as medication_name,
            om.ADMIN_ROUTE as route,
            COUNT(DISTINCT pat.PAT_MRN_ID || '-' || nm.NHSN_CODE || '-' || {date_expr}) as days_of_therapy
        FROM MAR_ADMIN_INFO mar
        JOIN ORDER_MED om ON mar.ORDER_MED_ID = om.ORDER_MED_ID
        JOIN RX_MED_ONE rx ON om.MEDICATION_ID = rx.MEDICATION_ID
        JOIN NHSN_ANTIMICROBIAL_MAP nm ON rx.MEDICATION_ID = nm.MEDICATION_ID
        JOIN PAT_ENC pe ON om.PAT_ENC_CSN_ID = pe.PAT_ENC_CSN_ID
        JOIN PATIENT pat ON pe.PAT_ID = pat.PAT_ID
        JOIN NHSN_LOCATION_MAP loc ON pe.DEPARTMENT_ID = loc.EPIC_DEPT_ID
        WHERE mar.ACTION_NAME = 'Given'
            AND mar.TAKEN_TIME >= :start_date
            AND mar.TAKEN_TIME <= :end_date
            {location_filter}
            {route_filter}
        GROUP BY loc.NHSN_LOCATION_CODE, {month_expr}, nm.NHSN_CODE, nm.NHSN_CATEGORY, rx.GENERIC_NAME, om.ADMIN_ROUTE
        ORDER BY {month_expr}, loc.NHSN_LOCATION_CODE, nm.NHSN_CATEGORY, nm.NHSN_CODE
        """

        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                df = pd.read_sql(
                    text(query), conn,
                    params={'start_date': start_date, 'end_date': end_date},
                )
                df.columns = df.columns.str.lower()
                return df
        except Exception as e:
            logger.error(f"DOT calculation query failed: {e}")
            return pd.DataFrame()

    def calculate_ddd(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        """Calculate Defined Daily Doses (DDD) by location, month, and antimicrobial."""
        import pandas as pd
        from sqlalchemy import text

        if start_date is None:
            start_date = date.today().replace(day=1)
        if end_date is None:
            end_date = date.today()

        location_filter = ""
        if locations:
            location_list = ", ".join(f"'{loc}'" for loc in locations)
            location_filter = f"AND loc.NHSN_LOCATION_CODE IN ({location_list})"

        if self._is_sqlite():
            month_expr = "strftime('%Y-%m', mar.TAKEN_TIME)"
        else:
            month_expr = "FORMAT(mar.TAKEN_TIME, 'yyyy-MM')"

        query = f"""
        SELECT
            loc.NHSN_LOCATION_CODE as nhsn_location_code,
            {month_expr} as month,
            nm.NHSN_CODE as nhsn_code,
            nm.NHSN_CATEGORY as nhsn_category,
            rx.GENERIC_NAME as medication_name,
            nm.DDD as ddd_standard,
            nm.DDD_UNIT as ddd_unit,
            SUM(CASE
                WHEN mar.DOSE_UNIT IN ('g', 'gram', 'grams') THEN mar.DOSE_GIVEN
                WHEN mar.DOSE_UNIT IN ('mg', 'milligram', 'milligrams') THEN mar.DOSE_GIVEN / 1000.0
                WHEN mar.DOSE_UNIT IN ('mcg', 'microgram', 'micrograms') THEN mar.DOSE_GIVEN / 1000000.0
                ELSE 0
            END) as total_grams,
            CASE
                WHEN nm.DDD > 0 THEN
                    SUM(CASE
                        WHEN mar.DOSE_UNIT IN ('g', 'gram', 'grams') THEN mar.DOSE_GIVEN
                        WHEN mar.DOSE_UNIT IN ('mg', 'milligram', 'milligrams') THEN mar.DOSE_GIVEN / 1000.0
                        WHEN mar.DOSE_UNIT IN ('mcg', 'microgram', 'micrograms') THEN mar.DOSE_GIVEN / 1000000.0
                        ELSE 0
                    END) / nm.DDD
                ELSE NULL
            END as defined_daily_doses
        FROM MAR_ADMIN_INFO mar
        JOIN ORDER_MED om ON mar.ORDER_MED_ID = om.ORDER_MED_ID
        JOIN RX_MED_ONE rx ON om.MEDICATION_ID = rx.MEDICATION_ID
        JOIN NHSN_ANTIMICROBIAL_MAP nm ON rx.MEDICATION_ID = nm.MEDICATION_ID
        JOIN PAT_ENC pe ON om.PAT_ENC_CSN_ID = pe.PAT_ENC_CSN_ID
        JOIN NHSN_LOCATION_MAP loc ON pe.DEPARTMENT_ID = loc.EPIC_DEPT_ID
        WHERE mar.ACTION_NAME = 'Given'
            AND mar.TAKEN_TIME >= :start_date
            AND mar.TAKEN_TIME <= :end_date
            {location_filter}
        GROUP BY loc.NHSN_LOCATION_CODE, {month_expr}, nm.NHSN_CODE, nm.NHSN_CATEGORY, rx.GENERIC_NAME, nm.DDD, nm.DDD_UNIT
        ORDER BY {month_expr}, loc.NHSN_LOCATION_CODE, nm.NHSN_CATEGORY, nm.NHSN_CODE
        """

        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                df = pd.read_sql(
                    text(query), conn,
                    params={'start_date': start_date, 'end_date': end_date},
                )
                df.columns = df.columns.str.lower()
                return df
        except Exception as e:
            logger.error(f"DDD calculation query failed: {e}")
            return pd.DataFrame()

    def get_monthly_summary(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        include_oral: bool | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive monthly AU summary for NHSN reporting."""
        import pandas as pd
        from .denominator import DenominatorCalculator

        dot_df = self.calculate_dot(locations, start_date, end_date, include_oral)
        ddd_df = self.calculate_ddd(locations, start_date, end_date)
        denom_calc = DenominatorCalculator(self.connection_string)
        patient_days_df = denom_calc.get_patient_days(locations, start_date, end_date)

        if dot_df.empty:
            return {
                'date_range': {
                    'start': str(start_date) if start_date else None,
                    'end': str(end_date) if end_date else None,
                },
                'locations': [],
                'overall_totals': {'total_dot': 0, 'total_patient_days': 0, 'dot_per_1000_pd': 0},
            }

        merged = pd.merge(
            dot_df,
            patient_days_df[['nhsn_location_code', 'month', 'patient_days']],
            on=['nhsn_location_code', 'month'],
            how='left',
        )
        merged['patient_days'] = merged['patient_days'].fillna(0).astype(int)
        merged['dot_per_1000_pd'] = merged.apply(
            lambda row: round(row['days_of_therapy'] / row['patient_days'] * 1000, 2)
            if row['patient_days'] > 0 else 0,
            axis=1,
        )

        if not ddd_df.empty:
            merged = pd.merge(
                merged,
                ddd_df[['nhsn_location_code', 'month', 'nhsn_code', 'defined_daily_doses']],
                on=['nhsn_location_code', 'month', 'nhsn_code'],
                how='left',
            )

        result = {
            'date_range': {
                'start': str(start_date) if start_date else None,
                'end': str(end_date) if end_date else None,
            },
            'locations': [],
            'overall_totals': {
                'total_dot': int(merged['days_of_therapy'].sum()),
                'total_patient_days': int(patient_days_df['patient_days'].sum()) if not patient_days_df.empty else 0,
            },
        }

        total_pd = result['overall_totals']['total_patient_days']
        result['overall_totals']['dot_per_1000_pd'] = (
            round(result['overall_totals']['total_dot'] / total_pd * 1000, 2)
            if total_pd > 0 else 0
        )

        for loc_code in sorted(merged['nhsn_location_code'].unique()):
            loc_data = merged[merged['nhsn_location_code'] == loc_code]
            loc_summary = {
                'nhsn_location_code': loc_code,
                'months': [],
                'totals': {
                    'total_dot': int(loc_data['days_of_therapy'].sum()),
                    'patient_days': int(loc_data['patient_days'].sum()),
                },
            }
            loc_pd = loc_summary['totals']['patient_days']
            loc_summary['totals']['dot_per_1000_pd'] = (
                round(loc_summary['totals']['total_dot'] / loc_pd * 1000, 2)
                if loc_pd > 0 else 0
            )

            for month in sorted(loc_data['month'].unique()):
                month_data = loc_data[loc_data['month'] == month]
                month_patient_days = int(month_data['patient_days'].iloc[0]) if len(month_data) > 0 else 0
                month_summary = {
                    'month': month,
                    'patient_days': month_patient_days,
                    'total_dot': int(month_data['days_of_therapy'].sum()),
                    'antimicrobials': [],
                }
                month_summary['dot_per_1000_pd'] = (
                    round(month_summary['total_dot'] / month_patient_days * 1000, 2)
                    if month_patient_days > 0 else 0
                )
                for _, row in month_data.iterrows():
                    antimicrobial = {
                        'nhsn_code': row['nhsn_code'],
                        'nhsn_category': row['nhsn_category'],
                        'medication_name': row['medication_name'],
                        'route': row['route'],
                        'days_of_therapy': int(row['days_of_therapy']),
                        'dot_per_1000_pd': row['dot_per_1000_pd'],
                    }
                    if 'defined_daily_doses' in row and pd.notna(row.get('defined_daily_doses')):
                        antimicrobial['defined_daily_doses'] = round(row['defined_daily_doses'], 2)
                    month_summary['antimicrobials'].append(antimicrobial)
                loc_summary['months'].append(month_summary)
            result['locations'].append(loc_summary)

        return result

    def export_for_nhsn(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        """Export AU data in NHSN CSV submission format."""
        import pandas as pd
        from .denominator import DenominatorCalculator

        dot_df = self.calculate_dot(locations, start_date, end_date)
        denom_calc = DenominatorCalculator(self.connection_string)
        patient_days_df = denom_calc.get_patient_days(locations, start_date, end_date)

        if dot_df.empty:
            return pd.DataFrame()

        merged = pd.merge(
            dot_df,
            patient_days_df[['nhsn_location_code', 'month', 'patient_days']],
            on=['nhsn_location_code', 'month'],
            how='left',
        )

        facility_id = cfg.get_facility_id()
        return pd.DataFrame({
            'orgID': facility_id,
            'locationCode': merged['nhsn_location_code'],
            'summaryYM': merged['month'].str.replace('-', ''),
            'antimicrobialCode': merged['nhsn_code'],
            'antimicrobialCategory': merged['nhsn_category'],
            'route': merged['route'],
            'daysOfTherapy': merged['days_of_therapy'],
            'patientDays': merged['patient_days'].fillna(0).astype(int),
        })
