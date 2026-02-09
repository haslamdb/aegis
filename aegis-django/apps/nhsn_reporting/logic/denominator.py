"""Denominator data aggregation for NHSN reporting.

Calculates device-days and patient-days from Clarity data
for NHSN monthly summary reporting.
"""

import logging
from datetime import date
from typing import Any

from . import config as cfg

logger = logging.getLogger(__name__)


class DenominatorCalculator:
    """Calculate device-days and patient-days from Clarity data."""

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

    def get_central_line_days(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        """Calculate central line days by location and month."""
        import pandas as pd
        from sqlalchemy import text

        if start_date is None:
            start_date = date.today().replace(year=date.today().year - 1)
        if end_date is None:
            end_date = date.today()

        if self._is_sqlite():
            month_expr = "strftime('%Y-%m', fm.RECORDED_TIME)"
            date_expr = "date(fm.RECORDED_TIME)"
        else:
            month_expr = "FORMAT(fm.RECORDED_TIME, 'yyyy-MM')"
            date_expr = "CONVERT(DATE, fm.RECORDED_TIME)"

        location_filter = ""
        if locations:
            location_list = ", ".join(f"'{loc}'" for loc in locations)
            location_filter = f"AND loc.NHSN_LOCATION_CODE IN ({location_list})"

        query = f"""
        SELECT
            loc.NHSN_LOCATION_CODE,
            {month_expr} AS month,
            COUNT(DISTINCT pe.PAT_ID || '-' || {date_expr}) AS central_line_days
        FROM IP_FLWSHT_MEAS fm
        JOIN IP_FLWSHT_REC rec ON fm.FSD_ID = rec.FSD_ID
        JOIN PAT_ENC pe ON rec.INPATIENT_DATA_ID = pe.INPATIENT_DATA_ID
        JOIN NHSN_LOCATION_MAP loc ON pe.DEPARTMENT_ID = loc.EPIC_DEPT_ID
        JOIN IP_FLO_GP_DATA fd ON fm.FLO_MEAS_ID = fd.FLO_MEAS_ID
        WHERE (fd.DISP_NAME LIKE '%central%line%' OR fd.DISP_NAME LIKE '%PICC%')
            AND fm.MEAS_VALUE NOT LIKE '%removed%'
            AND fm.RECORDED_TIME >= :start_date
            AND fm.RECORDED_TIME <= :end_date
            {location_filter}
        GROUP BY loc.NHSN_LOCATION_CODE, {month_expr}
        ORDER BY {month_expr}, loc.NHSN_LOCATION_CODE
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
            logger.error(f"Central line days query failed: {e}")
            return pd.DataFrame(columns=['nhsn_location_code', 'month', 'central_line_days'])

    def get_urinary_catheter_days(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        """Calculate urinary catheter days by location and month."""
        import pandas as pd
        from sqlalchemy import text

        if start_date is None:
            start_date = date.today().replace(year=date.today().year - 1)
        if end_date is None:
            end_date = date.today()

        if self._is_sqlite():
            month_expr = "strftime('%Y-%m', fm.RECORDED_TIME)"
            date_expr = "date(fm.RECORDED_TIME)"
        else:
            month_expr = "FORMAT(fm.RECORDED_TIME, 'yyyy-MM')"
            date_expr = "CONVERT(DATE, fm.RECORDED_TIME)"

        location_filter = ""
        if locations:
            location_list = ", ".join(f"'{loc}'" for loc in locations)
            location_filter = f"AND loc.NHSN_LOCATION_CODE IN ({location_list})"

        query = f"""
        SELECT
            loc.NHSN_LOCATION_CODE,
            {month_expr} AS month,
            COUNT(DISTINCT pe.PAT_ID || '-' || {date_expr}) AS urinary_catheter_days
        FROM IP_FLWSHT_MEAS fm
        JOIN IP_FLWSHT_REC rec ON fm.FSD_ID = rec.FSD_ID
        JOIN PAT_ENC pe ON rec.INPATIENT_DATA_ID = pe.INPATIENT_DATA_ID
        JOIN NHSN_LOCATION_MAP loc ON pe.DEPARTMENT_ID = loc.EPIC_DEPT_ID
        JOIN IP_FLO_GP_DATA fd ON fm.FLO_MEAS_ID = fd.FLO_MEAS_ID
        WHERE (fd.DISP_NAME LIKE '%foley%'
               OR fd.DISP_NAME LIKE '%urinary%catheter%'
               OR fd.DISP_NAME LIKE '%indwelling%catheter%')
            AND fm.MEAS_VALUE NOT LIKE '%removed%'
            AND fm.MEAS_VALUE NOT LIKE '%discontinued%'
            AND fm.RECORDED_TIME >= :start_date
            AND fm.RECORDED_TIME <= :end_date
            {location_filter}
        GROUP BY loc.NHSN_LOCATION_CODE, {month_expr}
        ORDER BY {month_expr}, loc.NHSN_LOCATION_CODE
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
            logger.error(f"Urinary catheter days query failed: {e}")
            return pd.DataFrame(columns=['nhsn_location_code', 'month', 'urinary_catheter_days'])

    def get_ventilator_days(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        """Calculate ventilator days by location and month."""
        import pandas as pd
        from sqlalchemy import text

        if start_date is None:
            start_date = date.today().replace(year=date.today().year - 1)
        if end_date is None:
            end_date = date.today()

        if self._is_sqlite():
            month_expr = "strftime('%Y-%m', fm.RECORDED_TIME)"
            date_expr = "date(fm.RECORDED_TIME)"
        else:
            month_expr = "FORMAT(fm.RECORDED_TIME, 'yyyy-MM')"
            date_expr = "CONVERT(DATE, fm.RECORDED_TIME)"

        location_filter = ""
        if locations:
            location_list = ", ".join(f"'{loc}'" for loc in locations)
            location_filter = f"AND loc.NHSN_LOCATION_CODE IN ({location_list})"

        query = f"""
        SELECT
            loc.NHSN_LOCATION_CODE,
            {month_expr} AS month,
            COUNT(DISTINCT pe.PAT_ID || '-' || {date_expr}) AS ventilator_days
        FROM IP_FLWSHT_MEAS fm
        JOIN IP_FLWSHT_REC rec ON fm.FSD_ID = rec.FSD_ID
        JOIN PAT_ENC pe ON rec.INPATIENT_DATA_ID = pe.INPATIENT_DATA_ID
        JOIN NHSN_LOCATION_MAP loc ON pe.DEPARTMENT_ID = loc.EPIC_DEPT_ID
        JOIN IP_FLO_GP_DATA fd ON fm.FLO_MEAS_ID = fd.FLO_MEAS_ID
        WHERE (fd.DISP_NAME LIKE '%ventilator%'
               OR fd.DISP_NAME LIKE '%mechanical%vent%'
               OR fd.DISP_NAME LIKE '%vent%mode%'
               OR fd.DISP_NAME LIKE '%intubat%')
            AND fm.MEAS_VALUE NOT LIKE '%removed%'
            AND fm.MEAS_VALUE NOT LIKE '%extubat%'
            AND fm.MEAS_VALUE NOT LIKE '%discontinued%'
            AND fm.RECORDED_TIME >= :start_date
            AND fm.RECORDED_TIME <= :end_date
            {location_filter}
        GROUP BY loc.NHSN_LOCATION_CODE, {month_expr}
        ORDER BY {month_expr}, loc.NHSN_LOCATION_CODE
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
            logger.error(f"Ventilator days query failed: {e}")
            return pd.DataFrame(columns=['nhsn_location_code', 'month', 'ventilator_days'])

    def get_patient_days(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        """Calculate patient days by location and month using recursive CTE."""
        import pandas as pd
        from sqlalchemy import text

        if start_date is None:
            start_date = date.today().replace(year=date.today().year - 1)
        if end_date is None:
            end_date = date.today()

        location_filter = ""
        if locations:
            location_list = ", ".join(f"'{loc}'" for loc in locations)
            location_filter = f"AND loc.NHSN_LOCATION_CODE IN ({location_list})"

        if self._is_sqlite():
            query = f"""
            WITH RECURSIVE stay_days AS (
                SELECT
                    pe.PAT_ENC_CSN_ID,
                    pe.DEPARTMENT_ID,
                    MAX(date(pe.HOSP_ADMIT_DTTM), date(:start_date)) AS census_date,
                    MIN(date(COALESCE(pe.HOSP_DISCH_DTTM, :end_date)), date(:end_date)) AS end_dt
                FROM PAT_ENC pe
                WHERE pe.HOSP_ADMIT_DTTM <= :end_date
                    AND (pe.HOSP_DISCH_DTTM IS NULL OR pe.HOSP_DISCH_DTTM >= :start_date)
                UNION ALL
                SELECT PAT_ENC_CSN_ID, DEPARTMENT_ID, date(census_date, '+1 day'), end_dt
                FROM stay_days
                WHERE census_date < end_dt
            )
            SELECT
                loc.NHSN_LOCATION_CODE,
                strftime('%Y-%m', sd.census_date) AS month,
                COUNT(*) AS patient_days
            FROM stay_days sd
            JOIN NHSN_LOCATION_MAP loc ON sd.DEPARTMENT_ID = loc.EPIC_DEPT_ID
            WHERE 1=1 {location_filter}
            GROUP BY loc.NHSN_LOCATION_CODE, strftime('%Y-%m', sd.census_date)
            ORDER BY month, loc.NHSN_LOCATION_CODE
            """
        else:
            query = f"""
            WITH stay_days AS (
                SELECT
                    pe.PAT_ENC_CSN_ID,
                    pe.DEPARTMENT_ID,
                    CAST(CASE WHEN pe.HOSP_ADMIT_DTTM > :start_date
                         THEN pe.HOSP_ADMIT_DTTM ELSE :start_date END AS DATE) AS census_date,
                    CAST(CASE WHEN pe.HOSP_DISCH_DTTM IS NULL OR pe.HOSP_DISCH_DTTM > :end_date
                         THEN :end_date ELSE pe.HOSP_DISCH_DTTM END AS DATE) AS end_dt
                FROM PAT_ENC pe
                WHERE pe.HOSP_ADMIT_DTTM <= :end_date
                    AND (pe.HOSP_DISCH_DTTM IS NULL OR pe.HOSP_DISCH_DTTM >= :start_date)
                UNION ALL
                SELECT PAT_ENC_CSN_ID, DEPARTMENT_ID, DATEADD(DAY, 1, census_date), end_dt
                FROM stay_days
                WHERE census_date < end_dt
            )
            SELECT
                loc.NHSN_LOCATION_CODE,
                FORMAT(sd.census_date, 'yyyy-MM') AS month,
                COUNT(*) AS patient_days
            FROM stay_days sd
            JOIN NHSN_LOCATION_MAP loc ON sd.DEPARTMENT_ID = loc.EPIC_DEPT_ID
            WHERE 1=1 {location_filter}
            GROUP BY loc.NHSN_LOCATION_CODE, FORMAT(sd.census_date, 'yyyy-MM')
            ORDER BY month, loc.NHSN_LOCATION_CODE
            OPTION (MAXRECURSION 366)
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
            logger.error(f"Patient days query failed: {e}")
            return pd.DataFrame(columns=['nhsn_location_code', 'month', 'patient_days'])

    def get_denominator_summary(
        self,
        locations: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Get combined denominator summary for NHSN submission."""
        import pandas as pd

        line_days_df = self.get_central_line_days(locations, start_date, end_date)
        catheter_days_df = self.get_urinary_catheter_days(locations, start_date, end_date)
        vent_days_df = self.get_ventilator_days(locations, start_date, end_date)
        patient_days_df = self.get_patient_days(locations, start_date, end_date)

        if all(df.empty for df in [line_days_df, catheter_days_df, vent_days_df, patient_days_df]):
            return {
                'date_range': {
                    'start': str(start_date) if start_date else None,
                    'end': str(end_date) if end_date else None,
                },
                'locations': [],
            }

        merged = patient_days_df[['nhsn_location_code', 'month', 'patient_days']].copy()

        for df, col in [
            (line_days_df, 'central_line_days'),
            (catheter_days_df, 'urinary_catheter_days'),
            (vent_days_df, 'ventilator_days'),
        ]:
            if not df.empty:
                merged = pd.merge(
                    merged, df[['nhsn_location_code', 'month', col]],
                    on=['nhsn_location_code', 'month'], how='outer',
                )

        merged = merged.fillna(0)
        for col in ['central_line_days', 'urinary_catheter_days', 'ventilator_days', 'patient_days']:
            if col not in merged.columns:
                merged[col] = 0

        result = {
            'date_range': {
                'start': str(start_date) if start_date else None,
                'end': str(end_date) if end_date else None,
            },
            'locations': [],
        }

        for loc_code in sorted(merged['nhsn_location_code'].unique()):
            loc_data = merged[merged['nhsn_location_code'] == loc_code]
            months = []
            for _, row in loc_data.iterrows():
                pd_val = int(row['patient_days'])
                cl = int(row['central_line_days'])
                uc = int(row['urinary_catheter_days'])
                vd = int(row['ventilator_days'])
                months.append({
                    'month': row['month'],
                    'patient_days': pd_val,
                    'central_line_days': cl,
                    'urinary_catheter_days': uc,
                    'ventilator_days': vd,
                    'central_line_utilization': round(cl / pd_val, 3) if pd_val > 0 else 0,
                    'urinary_catheter_utilization': round(uc / pd_val, 3) if pd_val > 0 else 0,
                    'ventilator_utilization': round(vd / pd_val, 3) if pd_val > 0 else 0,
                })

            total_pd = int(loc_data['patient_days'].sum())
            total_cl = int(loc_data['central_line_days'].sum())
            total_uc = int(loc_data['urinary_catheter_days'].sum())
            total_vd = int(loc_data['ventilator_days'].sum())
            totals = {
                'patient_days': total_pd,
                'central_line_days': total_cl,
                'urinary_catheter_days': total_uc,
                'ventilator_days': total_vd,
                'central_line_utilization': round(total_cl / total_pd, 3) if total_pd > 0 else 0,
                'urinary_catheter_utilization': round(total_uc / total_pd, 3) if total_pd > 0 else 0,
                'ventilator_utilization': round(total_vd / total_pd, 3) if total_pd > 0 else 0,
            }

            result['locations'].append({
                'nhsn_location_code': loc_code, 'months': months, 'totals': totals,
            })

        return result

    def get_clabsi_rate(self, clabsi_count, locations=None, start_date=None, end_date=None):
        """Calculate CLABSI rate per 1,000 central line days."""
        df = self.get_central_line_days(locations, start_date, end_date)
        total = int(df['central_line_days'].sum()) if not df.empty else 0
        rate = (clabsi_count / total * 1000) if total > 0 else 0
        return {'clabsi_count': clabsi_count, 'central_line_days': total, 'rate_per_1000': round(rate, 2)}

    def get_cauti_rate(self, cauti_count, locations=None, start_date=None, end_date=None):
        """Calculate CAUTI rate per 1,000 urinary catheter days."""
        df = self.get_urinary_catheter_days(locations, start_date, end_date)
        total = int(df['urinary_catheter_days'].sum()) if not df.empty else 0
        rate = (cauti_count / total * 1000) if total > 0 else 0
        return {'cauti_count': cauti_count, 'urinary_catheter_days': total, 'rate_per_1000': round(rate, 2)}

    def get_vae_rate(self, vae_count, locations=None, start_date=None, end_date=None):
        """Calculate VAE rate per 1,000 ventilator days."""
        df = self.get_ventilator_days(locations, start_date, end_date)
        total = int(df['ventilator_days'].sum()) if not df.empty else 0
        rate = (vae_count / total * 1000) if total > 0 else 0
        return {'vae_count': vae_count, 'ventilator_days': total, 'rate_per_1000': round(rate, 2)}
