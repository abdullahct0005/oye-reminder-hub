
import streamlit as st
import pandas as pd
import re
from urllib.parse import quote
from datetime import datetime

st.set_page_config(page_title="OYE Reminder Hub", page_icon="📚", layout="wide")

REQUIRED = ["employee's name", "Mob No", "Trainer Name"]
FIXED_COLUMNS = {
    "employee's name","Mob No","Store","duties","superior","Entry date","Zone",
    "Location","Active status","Trainer Name","Total Course pending",
    "Total Course Completed","Total Course Enrolled","TYPE"
}

def clean_phone(v):
    s = re.sub(r"\D", "", str(v))
    return "91" + s if len(s) == 10 else s

def split_name_emp(v):
    s = str(v)
    m = re.search(r"-(\d{5,})$", s)
    return (s[:m.start()].strip(), m.group(1)) if m else (s.strip(), "")

def course_columns(df):
    return [c for c in df.columns if c not in FIXED_COLUMNS]

def status_class(v):
    return "Completed" if str(v).strip().lower() == "completed" else "Pending"

def build_message(name, course, status, level, custom_text=""):
    if custom_text.strip():
        return custom_text.replace("{name}", str(name)).replace("{course}", str(course)).replace("{status}", str(status))
    if level == "First Reminder":
        return (
            f"Hi {name}, your *{course}* course on OYE is currently showing as *{status}*. "
            f"Please complete the course as soon as possible. This is mandatory."
        )
    if level == "Second Reminder":
        return (
            f"Reminder: Hi {name}, your *{course}* course is still showing as *{status}* on OYE. "
            f"Please complete the mandatory course immediately."
        )
    return (
        f"URGENT REMINDER: Hi {name}, your *{course}* course is still pending on OYE. "
        f"Please complete it immediately."
    )

@st.cache_data(show_spinner=False)
def load_report(file_bytes):
    return pd.read_excel(file_bytes)

# ---------- HEADER ----------
st.title("OYE Course Reminder Hub")
st.caption("Shared trainer dashboard • Upload OYE report • Select trainer • Send individual reminders")

if "campaign_state" not in st.session_state:
    st.session_state.campaign_state = {}

with st.sidebar:
    st.header("Admin / Report")
    uploaded = st.file_uploader("Upload latest OYE Excel", type=["xlsx", "xls"])
    st.caption("Upload the newest report whenever OYE completion status changes.")
    st.divider()
    st.header("How trainers use it")
    st.markdown(
        "1. Upload latest report\n"
        "2. Select your name\n"
        "3. Select course\n"
        "4. Open WhatsApp chat\n"
        "5. Send message\n"
        "6. Mark Sent + Next"
    )

if not uploaded:
    st.info("Upload the latest OYE Excel report from the left panel to start.")
    st.stop()

try:
    raw = load_report(uploaded.getvalue())
except Exception as e:
    st.error(f"Could not read the Excel file: {e}")
    st.stop()

missing = [c for c in REQUIRED if c not in raw.columns]
if missing:
    st.error("Missing required columns: " + ", ".join(missing))
    st.stop()

courses = course_columns(raw)
trainers = sorted(raw["Trainer Name"].dropna().astype(str).str.strip().unique())

if not courses:
    st.error("No OYE course columns were detected.")
    st.stop()

# ---------- SETTINGS ----------
a, b, c = st.columns(3)
with a:
    trainer = st.selectbox("Select Your Trainer Name", trainers)
with b:
    course = st.selectbox("Select Course", courses)
with c:
    reminder_level = st.selectbox(
        "Reminder Type",
        ["First Reminder", "Second Reminder", "Final / Urgent Reminder"]
    )

custom_template = st.text_area(
    "Optional custom message template",
    placeholder="Use {name}, {course}, and {status}. Leave blank to use the standard message.",
    height=85
)

data = raw[raw["Trainer Name"].astype(str).str.strip().eq(trainer)].copy()
data[["OEC Name", "Employee ID"]] = data["employee's name"].apply(
    lambda x: pd.Series(split_name_emp(x))
)
data["WhatsApp Phone"] = data["Mob No"].apply(clean_phone)
data["Course Status"] = data[course].fillna("Not started").astype(str).str.strip()
data["Campaign Status"] = data["Course Status"].apply(status_class)
data["Reminder Message"] = data.apply(
    lambda r: build_message(
        r["OEC Name"], course, r["Course Status"], reminder_level, custom_template
    ),
    axis=1
)
data["WhatsApp Link"] = data.apply(
    lambda r: f"https://wa.me/{r['WhatsApp Phone']}?text={quote(r['Reminder Message'])}",
    axis=1
)

pending = data[data["Campaign Status"] == "Pending"].reset_index(drop=True)
completed = data[data["Campaign Status"] == "Completed"].reset_index(drop=True)

campaign_key = f"{trainer}|{course}|{reminder_level}|{len(pending)}|{uploaded.name}"
if st.session_state.campaign_state.get("key") != campaign_key:
    st.session_state.campaign_state = {
        "key": campaign_key,
        "index": 0,
        "sent": set(),
        "started": False,
        "started_at": None
    }

state = st.session_state.campaign_state

# ---------- METRICS ----------
m1, m2, m3, m4 = st.columns(4)
m1.metric("My Total OECs", len(data))
m2.metric("Pending", len(pending))
m3.metric("Completed", len(completed))
m4.metric("Completion %", f"{(len(completed)/len(data)*100 if len(data) else 0):.1f}%")

if "TYPE" in data.columns:
    with st.expander("View channel/type summary"):
        summary = data.groupby("TYPE").agg(
            Total=("OEC Name","size"),
            Pending=("Campaign Status", lambda s: (s == "Pending").sum()),
            Completed=("Campaign Status", lambda s: (s == "Completed").sum())
        ).reset_index()
        st.dataframe(summary, use_container_width=True, hide_index=True)

st.divider()

# ---------- CAMPAIGN ----------
st.subheader("My WhatsApp Reminder Campaign")

if len(pending) == 0:
    st.success("No pending OECs for this course in the latest report.")
else:
    top1, top2, top3 = st.columns([1,1,2])
    with top1:
        if not state["started"]:
            if st.button("Start Campaign", type="primary", use_container_width=True):
                state["started"] = True
                state["started_at"] = datetime.now().strftime("%d-%m-%Y %I:%M %p")
                st.rerun()
        else:
            st.success("Campaign active")
    with top2:
        st.metric("Marked Sent", len(state["sent"]))
    with top3:
        if state["started_at"]:
            st.caption(f"Started: {state['started_at']}")

    idx = min(state["index"], len(pending)-1)
    p = pending.iloc[idx]

    st.markdown(f"### {idx+1}. {p['OEC Name']}")
    x1, x2, x3, x4 = st.columns(4)
    x1.write(f"**Phone:** {p['WhatsApp Phone']}")
    x2.write(f"**Store:** {p.get('Store','')}")
    x3.write(f"**Type:** {p.get('TYPE','')}")
    x4.write(f"**OYE Status:** {p['Course Status']}")

    message = st.text_area(
        "Message",
        value=p["Reminder Message"],
        height=120,
        key=f"message_{campaign_key}_{idx}"
    )
    live_link = f"https://wa.me/{p['WhatsApp Phone']}?text={quote(message)}"

    if state["started"]:
        st.link_button(
            "Open WhatsApp Chat",
            live_link,
            type="primary",
            use_container_width=True
        )
        st.caption("This opens the trainer's own normal WhatsApp or WhatsApp Business account, depending on the device.")
    else:
        st.info("Click Start Campaign to enable sending.")

    n1, n2, n3, n4 = st.columns(4)
    with n1:
        if st.button("Previous", disabled=(idx == 0), use_container_width=True):
            state["index"] -= 1
            st.rerun()
    with n2:
        if st.button("Mark Sent + Next", disabled=not state["started"], use_container_width=True):
            state["sent"].add(idx)
            if idx < len(pending)-1:
                state["index"] += 1
            st.rerun()
    with n3:
        if st.button("Skip", disabled=(idx >= len(pending)-1), use_container_width=True):
            state["index"] += 1
            st.rerun()
    with n4:
        if st.button("Reset My Session", use_container_width=True):
            st.session_state.campaign_state = {
                "key": campaign_key,
                "index": 0,
                "sent": set(),
                "started": False,
                "started_at": None
            }
            st.rerun()

st.divider()

# ---------- QUEUE ----------
st.subheader("My Pending Queue")
view = pending.copy()
view["Session Status"] = [
    "Marked Sent" if i in state["sent"] else "Pending Send"
    for i in range(len(view))
]

cols = ["OEC Name","Employee ID","WhatsApp Phone","Store","TYPE",
        "Course Status","Session Status","Reminder Message"]
available = [c for c in cols if c in view.columns]
st.dataframe(view[available], use_container_width=True, height=360)

st.download_button(
    "Download My Campaign Queue (CSV)",
    view[available].to_csv(index=False).encode("utf-8-sig"),
    file_name=f"OYE_{trainer.replace(' ','_')}_{course}.csv",
    mime="text/csv"
)

st.divider()
st.caption(
    "Shared-web version note: the current app processes the report during the active browser session. "
    "For permanent shared history, logins, and a central report database, connect the next version to Supabase/Firebase or an internal company system."
)
