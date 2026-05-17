import io
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

BASE = "https://api.openf1.org/v1"

DB = dict(
    host="localhost",
    port=5432,
    dbname="f1db",
    user="f1",
    password="f1pass",
)

TEAM_NAME = "Red Bull Racing"


def fetch_csv(endpoint: str, params: dict) -> pd.DataFrame:
    params = dict(params)
    params["csv"] = "true"
    url = f"{BASE}/{endpoint}"
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def df_to_rows(df: pd.DataFrame) -> list[tuple]:
    """
    Convierte un DataFrame a lista de tuplas con tipos Python nativos
    y reemplaza NaN/NaT por None para psycopg2.
    """
    if df.empty:
        return []
    df = df.astype(object).where(pd.notna(df), None)
    return [tuple(row) for row in df.to_numpy()]


def upsert_dim_session(conn, df):
    cols = [
        "session_key", "meeting_key", "year", "country_name", "location",
        "circuit_short_name", "session_name", "date_start", "date_end"
    ]
    df = df[cols].copy()
    df["date_start"] = pd.to_datetime(df["date_start"], utc=True, errors="coerce")
    df["date_end"] = pd.to_datetime(df["date_end"], utc=True, errors="coerce")

    rows = df_to_rows(df)
    if not rows:
        return

    sql = """
    INSERT INTO dim_session(
        session_key, meeting_key, year, country_name, location,
        circuit_short_name, session_name, date_start, date_end
    )
    VALUES %s
    ON CONFLICT (session_key) DO UPDATE SET
      meeting_key=EXCLUDED.meeting_key,
      year=EXCLUDED.year,
      country_name=EXCLUDED.country_name,
      location=EXCLUDED.location,
      circuit_short_name=EXCLUDED.circuit_short_name,
      session_name=EXCLUDED.session_name,
      date_start=EXCLUDED.date_start,
      date_end=EXCLUDED.date_end
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)


def upsert_dim_driver(conn, df):
    cols = ["session_key", "driver_number", "full_name", "name_acronym", "team_name", "team_colour"]
    df = df[cols].copy()

    rows = df_to_rows(df)
    if not rows:
        return

    sql = """
    INSERT INTO dim_driver(
        session_key, driver_number, full_name, name_acronym, team_name, team_colour
    )
    VALUES %s
    ON CONFLICT (session_key, driver_number) DO UPDATE SET
      full_name=EXCLUDED.full_name,
      name_acronym=EXCLUDED.name_acronym,
      team_name=EXCLUDED.team_name,
      team_colour=EXCLUDED.team_colour
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)


def upsert_fact_grid(conn, df):
    cols = ["session_key", "driver_number", "position"]
    df = df[cols].copy()
    df = df.rename(columns={"position": "grid_position"})

    rows = df_to_rows(df)
    if not rows:
        return

    sql = """
    INSERT INTO fact_grid(session_key, driver_number, grid_position)
    VALUES %s
    ON CONFLICT (session_key, driver_number) DO UPDATE SET
      grid_position=EXCLUDED.grid_position
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)


def upsert_fact_result(conn, df):
    keep = ["session_key", "driver_number", "position", "number_of_laps", "duration", "gap_to_leader", "status"]
    df = df[[c for c in keep if c in df.columns]].copy()

    for c in keep:
        if c not in df.columns:
            df[c] = None

    df = df[keep]

    rows = df_to_rows(df)
    if not rows:
        return

    sql = """
    INSERT INTO fact_result(
        session_key, driver_number, position, number_of_laps, duration, gap_to_leader, status
    )
    VALUES %s
    ON CONFLICT (session_key, driver_number) DO UPDATE SET
      position=EXCLUDED.position,
      number_of_laps=EXCLUDED.number_of_laps,
      duration=EXCLUDED.duration,
      gap_to_leader=EXCLUDED.gap_to_leader,
      status=EXCLUDED.status
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)


def upsert_fact_lap(conn, df):
    keep = [
        "session_key", "driver_number", "lap_number", "date_start", "lap_duration",
        "duration_sector_1", "duration_sector_2", "duration_sector_3", "is_pit_out_lap"
    ]
    df = df[[c for c in keep if c in df.columns]].copy()

    for c in keep:
        if c not in df.columns:
            df[c] = None

    df["date_start"] = pd.to_datetime(df["date_start"], utc=True, errors="coerce")
    df = df[keep]

    rows = df_to_rows(df)
    if not rows:
        return

    sql = """
    INSERT INTO fact_lap(
        session_key, driver_number, lap_number, date_start, lap_duration,
        duration_sector_1, duration_sector_2, duration_sector_3, is_pit_out_lap
    )
    VALUES %s
    ON CONFLICT (session_key, driver_number, lap_number) DO UPDATE SET
      date_start=EXCLUDED.date_start,
      lap_duration=EXCLUDED.lap_duration,
      duration_sector_1=EXCLUDED.duration_sector_1,
      duration_sector_2=EXCLUDED.duration_sector_2,
      duration_sector_3=EXCLUDED.duration_sector_3,
      is_pit_out_lap=EXCLUDED.is_pit_out_lap
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=5000)


def upsert_fact_stint(conn, df):
    keep = ["session_key", "driver_number", "stint_number", "compound", "lap_start", "lap_end", "tyre_age_at_start"]
    df = df[[c for c in keep if c in df.columns]].copy()

    for c in keep:
        if c not in df.columns:
            df[c] = None

    df = df[keep]

    rows = df_to_rows(df)
    if not rows:
        return

    sql = """
    INSERT INTO fact_stint(
        session_key, driver_number, stint_number, compound, lap_start, lap_end, tyre_age_at_start
    )
    VALUES %s
    ON CONFLICT (session_key, driver_number, stint_number) DO UPDATE SET
      compound=EXCLUDED.compound,
      lap_start=EXCLUDED.lap_start,
      lap_end=EXCLUDED.lap_end,
      tyre_age_at_start=EXCLUDED.tyre_age_at_start
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)


def upsert_fact_pit(conn, df):
    keep = ["session_key", "driver_number", "lap_number", "date", "lane_duration", "stop_duration"]
    df = df[[c for c in keep if c in df.columns]].copy()

    for c in keep:
        if c not in df.columns:
            df[c] = None

    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    df = df[keep]

    rows = df_to_rows(df)
    if not rows:
        return

    sql = """
    INSERT INTO fact_pit(
        session_key, driver_number, lap_number, date, lane_duration, stop_duration
    )
    VALUES %s
    ON CONFLICT (session_key, driver_number, lap_number) DO UPDATE SET
      date=EXCLUDED.date,
      lane_duration=EXCLUDED.lane_duration,
      stop_duration=EXCLUDED.stop_duration
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=2000)


def infer_grid_from_position(session_key: int, meeting_key: int | None, driver_numbers: list[int]) -> pd.DataFrame:
    rows = []

    for dn in driver_numbers:
        # Intento 1: filtrar por session_key
        df = fetch_csv("position", {"session_key": session_key, "driver_number": int(dn)})

        # Intento 2: si viene vacío, probamos con meeting_key y luego filtramos por session_key
        if df.empty and meeting_key is not None:
            df = fetch_csv("position", {"meeting_key": int(meeting_key), "driver_number": int(dn)})
            if "session_key" in df.columns:
                df = df[df["session_key"] == session_key]

        if df.empty:
            continue

        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
        first = df.iloc[0]

        rows.append(
            {
                "session_key": int(session_key),
                "driver_number": int(dn),
                "position": int(first["position"]),  # usamos esto como grid_position aproximada
            }
        )

    return pd.DataFrame(rows)


def main():
    # 1) sesiones Race 2024
    sessions = fetch_csv("sessions", {"year": 2024, "session_name": "Race"})
    sessions = sessions.sort_values("date_start")

    if sessions.empty:
        print("No sessions found")
        return

    # Cogemos la primera carrera para test
    s = sessions.iloc[0]
    session_key = int(s["session_key"])
    print("Using session_key:", session_key)

    # 2) guardar sesiones en dim_session (todas las Race 2024)
    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    try:
        upsert_dim_session(conn, sessions)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # 3) drivers de esa carrera
    drivers = fetch_csv("drivers", {"session_key": session_key})
    rb = drivers[drivers["team_name"] == TEAM_NAME].copy()

    if rb.empty:
        print("No Red Bull drivers found for this session_key. Check team_name values.")
        if "team_name" in drivers.columns:
            print(drivers[["team_name"]].drop_duplicates().head(20))
        return

    rb_numbers = rb["driver_number"].astype(int).tolist()
    print("Red Bull driver_numbers:", rb_numbers)

    # guardamos dim_driver
    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    try:
        upsert_dim_driver(conn, rb)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # 4) grid + result (filtrados a Red Bull)
    meeting_key = int(s["meeting_key"]) if "meeting_key" in s and pd.notna(s["meeting_key"]) else None

    try:
        grid = fetch_csv("starting_grid", {"session_key": session_key})
        grid_rb = grid[grid["driver_number"].isin(rb_numbers)].copy()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            print("starting_grid no disponible (404). Infiriendo posición inicial con /position ...")
            grid_rb = infer_grid_from_position(session_key, meeting_key, rb_numbers)
        else:
            raise

    result = fetch_csv("session_result", {"session_key": session_key})
    result_rb = result[result["driver_number"].isin(rb_numbers)].copy()

    # 5) laps + stints + pit por piloto Red Bull
    laps_all = []
    stints_all = []
    pit_all = []

    for dn in rb_numbers:
        laps_dn = fetch_csv("laps", {"session_key": session_key, "driver_number": int(dn)})
        stints_dn = fetch_csv("stints", {"session_key": session_key, "driver_number": int(dn)})
        pit_dn = fetch_csv("pit", {"session_key": session_key, "driver_number": int(dn)})

        if not laps_dn.empty:
            laps_all.append(laps_dn)
        if not stints_dn.empty:
            stints_all.append(stints_dn)
        if not pit_dn.empty:
            pit_all.append(pit_dn)

    laps = pd.concat(laps_all, ignore_index=True) if laps_all else pd.DataFrame()
    stints = pd.concat(stints_all, ignore_index=True) if stints_all else pd.DataFrame()
    pit = pd.concat(pit_all, ignore_index=True) if pit_all else pd.DataFrame()

    # 6) cargar hechos
    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    try:
        if not grid_rb.empty:
            upsert_fact_grid(conn, grid_rb)
        if not result_rb.empty:
            upsert_fact_result(conn, result_rb)
        if not laps.empty:
            upsert_fact_lap(conn, laps)
        if not stints.empty:
            upsert_fact_stint(conn, stints)
        if not pit.empty:
            upsert_fact_pit(conn, pit)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("Loaded ✅")


if __name__ == "__main__":
    main()