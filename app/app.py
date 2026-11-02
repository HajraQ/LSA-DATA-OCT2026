import os
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

try:
    ROOT = Path(__file__).resolve().parent.parent
except NameError:
    ROOT = Path.cwd()
DB = Path(os.environ.get("LSA_WAREHOUSE", ROOT / "warehouse" / "warehouse.duckdb"))

SOURCE = "Source: NHS England, Appointments in General Practice (warehouse table fact_appointments_monthly)."
GENERAL = "Not all practices in England are included, and data quality varies between practices."

st.set_page_config(page_title="GP appointments: how is capacity used?", layout="wide")
st.title("How is GP appointment capacity being used, and where is it being lost?")
st.write("A dashboard for an NHS primary care manager. England, January 2020 to June 2022.")

if not DB.exists():
    st.error(f"Warehouse not found at {DB}. Build it first with: python run_pipeline.py")
    st.stop()


@st.cache_data
def query(sql):
    con = duckdb.connect(str(DB), read_only=True)
    try:
        return con.execute(sql).df()
    finally:
        con.close()


def month_name(ts):
    return pd.Timestamp(ts).strftime("%b %Y")


# ---------------------------------------------------------------- 1. volumes
st.header("1. How did appointment volumes change from 2020 to 2022?")
monthly = query("""SELECT month_start, sum(count_of_appointments) AS appointments
                   FROM fact_appointments_monthly GROUP BY 1 ORDER BY 1""")
monthly["month_start"] = pd.to_datetime(monthly["month_start"])
monthly["millions"] = monthly["appointments"] / 1e6
first = monthly.iloc[0]
low = monthly.loc[monthly["millions"].idxmin()]
change = 100 * (low["millions"] / first["millions"] - 1)
st.markdown(f"**Finding:** appointments fell from {first['millions']:.1f} million in {month_name(first['month_start'])} "
            f"to {low['millions']:.1f} million in {month_name(low['month_start'])} ({change:+.0f}%).")
fig1 = px.line(monthly, x="month_start", y="millions", markers=True,
               labels={"month_start": "Month", "millions": "Appointments (millions)"})
label = "COVID-19: first lockdown" if pd.Timestamp(low["month_start"]) == pd.Timestamp("2020-04-01") else "Lowest month"
fig1.add_annotation(x=low["month_start"], y=low["millions"], text=label, showarrow=True, arrowhead=2, ay=40)
fig1.update_yaxes(rangemode="tozero")
st.plotly_chart(fig1)
st.caption(f"{SOURCE} Caveat: {GENERAL} Totals are estimates of activity, not of demand or capacity.")

# ---------------------------------------------------------------- 2. missed appointments
st.header("2. What share of appointments are missed (DNA), and is it rising or falling?")
status = query("""SELECT month_start, appointment_status, sum(count_of_appointments) AS n
                  FROM fact_appointments_monthly GROUP BY 1, 2 ORDER BY 1""")
wide = status.pivot(index="month_start", columns="appointment_status", values="n").fillna(0)
wide.index = pd.to_datetime(wide.index)
known = wide["DNA"] + wide["Attended"]
dna = pd.DataFrame({"dna_pct": 100 * wide["DNA"] / known,
                    "unknown_pct": 100 * wide["Unknown"] / wide.sum(axis=1)}).reset_index()
d_first, d_last = dna.iloc[0], dna.iloc[-1]
d_lo, d_hi = dna.loc[dna["dna_pct"].idxmin()], dna.loc[dna["dna_pct"].idxmax()]
st.markdown(f"**Finding:** {d_first['dna_pct']:.1f}% in {month_name(d_first['month_start'])}, "
            f"{d_last['dna_pct']:.1f}% in {month_name(d_last['month_start'])}. "
            f"Lowest {d_lo['dna_pct']:.1f}% ({month_name(d_lo['month_start'])}), "
            f"highest {d_hi['dna_pct']:.1f}% ({month_name(d_hi['month_start'])}).")
fig2 = px.line(dna, x="month_start", y="dna_pct", markers=True,
               labels={"month_start": "Month", "dna_pct": "DNA as % of appointments with a known outcome"})
fig2.update_yaxes(rangemode="tozero")
st.plotly_chart(fig2)
st.caption(f"{SOURCE} Caveat: share of Attended + DNA only. Appointments with Unknown status "
           f"({dna['unknown_pct'].min():.1f}% to {dna['unknown_pct'].max():.1f}% each month, highest in "
           f"{month_name(dna.loc[dna['unknown_pct'].idxmax(), 'month_start'])}) are excluded, "
           f"so we do not know whether they took place. {GENERAL}")

# ---------------------------------------------------------------- 3. waits by mode
st.header("3. How long do patients wait between booking and appointment, by mode?")
waits = query("""SELECT f.appointment_mode AS appt_mode, f.booking_wait AS wait_band, d.sort_order,
                        sum(f.count_of_appointments) AS n
                 FROM fact_appointments_monthly f
                 JOIN dim_booking_wait d ON f.booking_wait = d.booking_wait
                 GROUP BY 1, 2, 3""")
unknown_wait = waits["wait_band"] == "Unknown / Data Quality"
unknown_mode = waits["appt_mode"].str.lower().str.contains("unknown")
pct_unknown_wait = 100 * waits.loc[unknown_wait, "n"].sum() / waits["n"].sum()
pct_unknown_mode = 100 * waits.loc[unknown_mode, "n"].sum() / waits["n"].sum()
use = waits[~unknown_wait & ~unknown_mode].copy()
use["pct"] = 100 * use["n"] / use.groupby("appt_mode")["n"].transform("sum")
order = use.drop_duplicates("wait_band").sort_values("sort_order")["wait_band"].tolist()
table = use.pivot(index="appt_mode", columns="wait_band", values="pct")[order]
volume = use.groupby("appt_mode")["n"].sum()
summary = pd.DataFrame({
    f"Seen within 1 day (%) [{order[0]} + {order[1]}]": table[order[:2]].sum(axis=1).round(1),
    "Waiting 15 days or more (%)": table[order[4:]].sum(axis=1).round(1),
    "Appointments (millions)": (volume / 1e6).round(1),
})
st.markdown("**Finding:** see the table. The shares of appointments seen within one day and waiting 15 days or more differ by mode.")
st.dataframe(summary)
fig3 = px.bar(use.sort_values("sort_order"), x="pct", y="appt_mode", color="wait_band", orientation="h",
              category_orders={"wait_band": order}, barmode="stack",
              labels={"pct": "% of appointments in the mode", "appt_mode": "Mode", "wait_band": "Wait"})
st.plotly_chart(fig3)
small = volume[volume / volume.sum() < 0.02].index.tolist()
small_note = (f" {', '.join(small)} are small modes (under 2% of appointments each), so read their shares with care."
              if small else "")
st.caption(f"{SOURCE} Caveat: mode is set locally by each practice and may not match the real mode; "
           f"online appointments may not include a video element.{small_note} "
           f"Left out: Unknown wait band ({pct_unknown_wait:.1f}% of appointments) and Unknown mode "
           f"({pct_unknown_mode:.1f}%). {GENERAL}")

with st.expander("About the data"):
    st.write("Data: NHS England, Appointments in General Practice, built with PySpark and DuckDB. "
             "It is aggregated counts only. It must not be combined with other data to identify a practice or a person.")
