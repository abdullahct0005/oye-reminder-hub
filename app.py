import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
import json
from io import BytesIO
from urllib.parse import quote
from datetime import datetime

# ============================================================
# OYE REMINDER + TRAINING REMINDER HUB
# One reusable WhatsApp Web tab
# Course auto-detection + personalized messages + batch queue
# ============================================================

st.set_page_config(
    page_title="OYE & Training Reminder Hub",
    page_icon="📚",
    layout="wide"
)

BATCH_SIZE = 10

OYE_FIXED_COLUMNS = {
    "employee's name", "mob no", "store", "duties", "superior",
    "entry date", "zone", "location", "active status",
    "trainer name", "total course pending", "total course completed",
    "total course enrolled", "type"
}

NAME_CANDIDATES = [
    "employee's name", "employee name", "oec name", "name",
    "employee", "participant name", "participant"
]
PHONE_CANDIDATES = [
    "mob no", "mobile", "mobile no", "phone", "phone number",
    "whatsapp", "whatsapp number", "contact number", "contact"
]
TRAINER_CANDIDATES = ["trainer name", "trainer", "trainer name/id"]


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def clean_phone(value):
    """Returns (91XXXXXXXXXX, True) or ('', False)."""
    if pd.isna(value):
        return "", False

    value = str(value).strip()
    value = re.sub(r"\.0$", "", value)
    digits = re.sub(r"\D", "", value)

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]

    if len(digits) == 10 and digits[0] in "6789":
        return "91" + digits, True

    return "", False


def find_column(df, candidates):
    lower_map = {str(col).strip().lower(): col for col in df.columns}

    for candidate in candidates:
        if candidate in lower_map:
            return lower_map[candidate]

    for col in df.columns:
        col_lower = str(col).strip().lower()
        for candidate in candidates:
            if candidate in col_lower:
                return col

    return None


def get_course_columns(df):
    """Detect all course columns automatically from a new OYE report."""
    courses = []
    for column in df.columns:
        if str(column).strip().lower() not in OYE_FIXED_COLUMNS:
            courses.append(column)
    return courses


def is_completed(value):
    return clean_text(value).lower() == "completed"


def get_status(value):
    value = clean_text(value)
    return value if value else "Not started"


def build_message(name, course, status, template):
    """
    Supported placeholders:
    {name}
    {course}
    {status}

    If no custom template is entered, a personalized default is used.
    """
    name = clean_text(name)
    course = clean_text(course)
    status = clean_text(status)

    if template.strip():
        return (
            template
            .replace("{name}", name)
            .replace("{course}", course)
            .replace("{status}", status)
        )

    return (
        f"Hi {name},\n\n"
        f"Your *{course}* is currently showing as *{status}* on OYE.\n\n"
        f"Please complete the course as soon as possible. This is mandatory."
    )


def make_whatsapp_url(phone, message):
    return f"https://web.whatsapp.com/send?phone={phone}&text={quote(message)}"


def load_excel(file_bytes):
    return pd.read_excel(BytesIO(file_bytes))


def load_roster(file):
    if file.name.lower().endswith(".csv"):
        return pd.read_csv(file)
    return pd.read_excel(file)


def init_state():
    defaults = {
        "mode": "OYE Course Reminder",
        "batch_number": 0,
        "sent_ids": set(),
        "campaign_signature": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_campaign(signature=None):
    st.session_state.batch_number = 0
    st.session_state.sent_ids = set()
    st.session_state.campaign_signature = signature


def campaign_table(rows, campaign_id):
    if not rows:
        return

    # Current batch, excluding manually marked-sent people
    active_rows = [
        row for row in rows
        if row["id"] not in st.session_state.sent_ids
    ]

    start = st.session_state.batch_number * BATCH_SIZE
    end = start + BATCH_SIZE
    batch = active_rows[start:end]

    if not batch and st.session_state.batch_number > 0:
        st.session_state.batch_number -= 1
        st.rerun()

    total_batches = max(1, (len(active_rows) + BATCH_SIZE - 1) // BATCH_SIZE)

    nav1, nav2, nav3 = st.columns([1, 2, 1])
    with nav1:
        if st.button("← Previous Batch", disabled=st.session_state.batch_number == 0, key=f"prev_{campaign_id}"):
            st.session_state.batch_number -= 1
            st.rerun()

    with nav2:
        st.markdown(
            f"<div style='text-align:center;padding:8px 0;'>"
            f"<b>Batch {st.session_state.batch_number + 1} of {total_batches}</b> "
            f"• Showing {len(batch)} pending people"
            f"</div>",
            unsafe_allow_html=True
        )

    with nav3:
        if st.button(
            "Next Batch →",
            disabled=(st.session_state.batch_number >= total_batches - 1),
            key=f"next_{campaign_id}"
        ):
            st.session_state.batch_number += 1
            st.rerun()

    st.divider()

    # --------------------------------------------------------
    # ONE reusable WhatsApp Web window controller
    #
    # IMPORTANT: This is ONE component containing all 10 drafts.
    # Every click calls window.open(url, 'oye_whatsapp_window').
    # Therefore the same named browser tab/window is reused.
    # --------------------------------------------------------
    valid_batch = [row for row in batch if row["phone_valid"]]
    queue_payload = [
        {
            "name": row["name"],
            "url": row["url"],
            "index": i + 1
        }
        for i, row in enumerate(valid_batch)
    ]

    if queue_payload:
        queue_json = json.dumps(queue_payload).replace("</", "<\\/")
        controller_html = f"""
        <div id="oye-wa-queue" style="
            border:1px solid #334155;
            border-radius:12px;
            padding:18px;
            margin:6px 0 18px 0;
            font-family:Arial,sans-serif;
            background:#111827;
            color:#e5e7eb;
        ">
            <div style="font-size:20px;font-weight:700;margin-bottom:8px;">
                WhatsApp Batch Queue
            </div>
            <div style="color:#9ca3af;margin-bottom:14px;">
                One reusable WhatsApp Web tab. Open each personalized draft and manually click Send in WhatsApp.
            </div>

            <div id="queue-status" style="
                padding:12px;
                border-radius:8px;
                background:#1f2937;
                margin-bottom:12px;
            "></div>

            <button id="open-current" style="
                width:100%;
                padding:14px;
                border:none;
                border-radius:8px;
                font-size:16px;
                font-weight:700;
                cursor:pointer;
                background:#25D366;
                color:#07130b;
            ">Open Current WhatsApp Draft</button>

            <div style="display:flex;gap:10px;margin-top:10px;">
                <button id="previous" style="flex:1;padding:10px;border-radius:8px;border:1px solid #475569;background:#1f2937;color:#fff;cursor:pointer;">
                    ← Previous
                </button>
                <button id="next" style="flex:1;padding:10px;border-radius:8px;border:1px solid #475569;background:#1f2937;color:#fff;cursor:pointer;">
                    Next Draft →
                </button>
            </div>

            <div style="font-size:12px;color:#94a3b8;margin-top:12px;">
                Keep the WhatsApp tab open. Every new draft reuses the same named tab: oye_whatsapp_window.
            </div>
        </div>

        <script>
        const queue = {queue_json};
        let current = 0;
        let waWindow = null;

        function renderQueue() {{
            const status = document.getElementById("queue-status");
            if (!queue.length) {{
                status.innerHTML = "No valid phone numbers in this batch.";
                return;
            }}
            status.innerHTML =
                "<b>Draft " + (current + 1) + " of " + queue.length + "</b><br>" +
                "OEC: " + queue[current].name;
        }}

        function openCurrent() {{
            if (!queue.length) return;

            const url = queue[current].url;

            // Reuse the SAME named browser window/tab.
            if (waWindow && !waWindow.closed) {{
                waWindow.location.href = url;
                waWindow.focus();
            }} else {{
                waWindow = window.open(url, "oye_whatsapp_window");
            }}

            if (waWindow) {{
                waWindow.focus();
            }}

            renderQueue();
        }}

        document.getElementById("open-current").addEventListener("click", openCurrent);

        document.getElementById("next").addEventListener("click", function() {{
            if (current < queue.length - 1) {{
                current += 1;
                renderQueue();
            }}
        }});

        document.getElementById("previous").addEventListener("click", function() {{
            if (current > 0) {{
                current -= 1;
                renderQueue();
            }}
        }});

        renderQueue();
        </script>
        """
        components.html(controller_html, height=265, scrolling=False)
    else:
        st.warning("No valid WhatsApp numbers are available in this batch.")

    # --------------------------------------------------------
    # SIMPLE LIST ONLY - no huge message under each name
    # --------------------------------------------------------
    st.subheader(f"Current Batch – {len(batch)} People")

    for i, row in enumerate(batch, start=1):
        with st.container(border=True):
            left, middle, right = st.columns([1.2, 2.4, 1.2])

            with left:
                st.markdown(f"**{i}. {row['name']}**")
                if row.get("employee_id"):
                    st.caption(f"ID: {row['employee_id']}")
                if row.get("group"):
                    st.caption(f"Group: {row['group']}")

            with middle:
                if row.get("store"):
                    st.write(f"**Store:** {row['store']}")
                if row.get("course"):
                    st.write(f"**Course:** {row['course']}")
                if row.get("status"):
                    st.write(f"**Status:** {row['status']}")
                if row.get("training_date"):
                    st.write(f"**Training:** {row['training_date']}")

            with right:
                if row["phone_valid"]:
                    st.success("Number Updated")
                    st.caption(row["phone_display"])
                else:
                    st.error("Number not updated in the system")
                    if row["phone_display"]:
                        st.caption(f"Entered: {row['phone_display']}")

                mark_key = f"sent_{campaign_id}_{row['id']}"
                if st.button(
                    "✓ Mark as Sent",
                    key=mark_key,
                    disabled=(row["id"] in st.session_state.sent_ids)
                ):
                    st.session_state.sent_ids.add(row["id"])
                    st.rerun()

    st.divider()

    sent_count = sum(1 for row in rows if row["id"] in st.session_state.sent_ids)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total pending", len(rows))
    c2.metric("Marked sent", sent_count)
    c3.metric("Remaining", len(rows) - sent_count)

    # Download queue
    export_rows = []
    for row in active_rows:
        export_rows.append({
            "Name": row["name"],
            "Phone": row["phone_display"],
            "Group": row.get("group", ""),
            "Course": row.get("course", ""),
            "Status": row.get("status", ""),
            "Store": row.get("store", ""),
            "Training": row.get("training_date", ""),
            "Phone Valid": row["phone_valid"]
        })

    if export_rows:
        export_df = pd.DataFrame(export_rows)
        st.download_button(
            "Download Remaining Queue (CSV)",
            export_df.to_csv(index=False).encode("utf-8"),
            file_name=f"remaining_queue_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            key=f"download_{campaign_id}"
        )


# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------

init_state()

with st.sidebar:
    st.header("Reminder Hub")
    mode = st.radio(
        "Choose campaign",
        ["OYE Course Reminder", "Training Reminder"],
        index=0 if st.session_state.mode == "OYE Course Reminder" else 1
    )
    st.session_state.mode = mode

    st.divider()
    st.header("How it works")

    st.markdown(
        """
        **OYE Course Reminder**
        1. Upload latest OYE Excel
        2. Select trainer
        3. Select automatically detected course
        4. Start campaign
        5. Work in batches of 10

        **Training Reminder**
        1. Upload participant Excel/CSV
        2. Enter training details
        3. Prepare personalized reminders
        4. Use the same WhatsApp Web tab
        """
    )


# ============================================================
# OYE COURSE REMINDER MODE
# ============================================================

if mode == "OYE Course Reminder":
    st.title("OYE Course Reminder Hub")
    st.caption("New course columns are detected automatically from the latest OYE Excel report.")

    uploaded_file = st.file_uploader(
        "Upload latest OYE Excel",
        type=["xlsx", "xls"],
        key="oye_upload"
    )

    if uploaded_file is None:
        st.info("Upload the latest OYE Excel report to start.")
        st.stop()

    try:
        df = load_excel(uploaded_file.getvalue())
    except Exception as e:
        st.error(f"Could not read the Excel file: {e}")
        st.stop()

    name_col = find_column(df, NAME_CANDIDATES)
    phone_col = find_column(df, PHONE_CANDIDATES)
    trainer_col = find_column(df, TRAINER_CANDIDATES)

    if not name_col or not phone_col:
        st.error(
            "Could not find the name or phone column. "
            "Please ensure the Excel contains employee/OEC name and Mob No/phone columns."
        )
        st.stop()

    course_columns = get_course_columns(df)

    if not course_columns:
        st.error("No course columns were detected in this Excel.")
        st.stop()

    if trainer_col:
        trainers = sorted(
            x for x in df[trainer_col].dropna().astype(str).unique()
            if x.strip()
        )
        trainer_choice = st.selectbox("Select your trainer name", trainers)
        trainer_df = df[
            df[trainer_col].astype(str).str.strip() == str(trainer_choice).strip()
        ].copy()
    else:
        st.warning("Trainer column was not found. The full uploaded report will be used.")
        trainer_choice = "All"
        trainer_df = df.copy()

    course = st.selectbox("Select course", course_columns)

    custom_template = st.text_area(
        "Optional custom message",
        placeholder=(
            "Example:\n"
            "Hi {name}, your *{course}* course status is *{status}*. "
            "Please complete it today."
        ),
        help="The app automatically replaces {name}, {course} and {status}."
    )

    st.info(
        "You do not need to rewrite the name or course for every person. "
        "When a new OYE report is uploaded, new course columns are detected automatically."
    )

    signature = (
        f"oye|{uploaded_file.name}|{trainer_choice}|{course}|"
        f"{hash(custom_template)}"
    )

    if st.session_state.campaign_signature != signature:
        reset_campaign(signature)

    if st.button("Start / Refresh Campaign", type="primary"):
        reset_campaign(signature)

    pending_df = trainer_df[
        ~trainer_df[course].apply(is_completed)
    ].copy()

    rows = []

    for index, row in pending_df.iterrows():
        name = clean_text(row[name_col])
        phone_raw = row[phone_col]
        phone, phone_valid = clean_phone(phone_raw)
        status = get_status(row[course])
        message = build_message(
            name=name,
            course=str(course),
            status=status,
            template=custom_template
        )

        employee_id = ""
        match = re.search(r"(\d{5,})$", name)
        if match:
            employee_id = match.group(1)

        store_col = find_column(df, ["store"])
        type_col = find_column(df, ["type"])

        rows.append({
            "id": f"oye_{index}_{course}",
            "name": name,
            "employee_id": employee_id,
            "phone_valid": phone_valid,
            "phone_display": clean_text(phone_raw),
            "store": clean_text(row[store_col]) if store_col else "",
            "group": clean_text(row[type_col]) if type_col else "",
            "course": str(course),
            "status": status,
            "training_date": "",
            "message": message,
            "url": make_whatsapp_url(phone, message) if phone_valid else ""
        })

    total = len(rows)
    completed = len(trainer_df) - total
    m1, m2, m3 = st.columns(3)
    m1.metric("Selected trainer OECs", len(trainer_df))
    m2.metric("Completed", completed)
    m3.metric("Pending", total)

    if not rows:
        st.success("No pending OECs for this course.")
        st.stop()

    campaign_table(rows, "oye")


# ============================================================
# TRAINING REMINDER MODE
# ============================================================

else:
    st.title("Training Reminder Hub")
    st.caption(
        "For GT, MT, OPC or any training program. Upload a participant list and send personalized training reminders."
    )

    roster_file = st.file_uploader(
        "Upload participant list",
        type=["xlsx", "xls", "csv"],
        key="training_roster"
    )

    st.info(
        "Recommended format: Excel/CSV with columns such as **Name**, **Phone**, and optional **Group/Type**. "
        "Image uploads are not recommended for contact lists because phone numbers can be misread by OCR."
    )

    if roster_file is None:
        st.stop()

    try:
        roster = load_roster(roster_file)
    except Exception as e:
        st.error(f"Could not read the participant file: {e}")
        st.stop()

    roster_name_col = find_column(roster, NAME_CANDIDATES)
    roster_phone_col = find_column(roster, PHONE_CANDIDATES)
    roster_group_col = find_column(roster, ["type", "group", "category", "channel"])

    if not roster_name_col or not roster_phone_col:
        st.error(
            "The participant file must contain a name column and a phone/mobile column."
        )
        st.stop()

    t1, t2, t3 = st.columns(3)
    with t1:
        training_name = st.text_input(
            "Training name",
            placeholder="Example: Reno16 GT Training"
        )
    with t2:
        training_date = st.date_input("Training date")
    with t3:
        training_time = st.text_input(
            "Training time",
            placeholder="Example: 10:00 AM"
        )

    training_mode = st.text_input(
        "Training type / venue / link",
        placeholder="Example: MT Training, Calicut Regional Office"
    )

    training_template = st.text_area(
        "Training reminder message",
        value=(
            "Hi {name},\n\n"
            "This is a reminder that you have *{training_name}* on *{date}* "
            "at *{time}*.\n\n"
            "Details: *{details}*\n\n"
            "Everyone should join the training on time."
        ),
        help="Supported: {name}, {training_name}, {date}, {time}, {details}, {group}"
    )

    group_filter = "All"
    if roster_group_col:
        groups = ["All"] + sorted(
            x for x in roster[roster_group_col].dropna().astype(str).unique()
            if x.strip()
        )
        group_filter = st.selectbox("Filter group/type", groups)

    training_signature = (
        f"training|{roster_file.name}|{training_name}|{training_date}|"
        f"{training_time}|{training_mode}|{group_filter}|{hash(training_template)}"
    )

    if st.session_state.campaign_signature != training_signature:
        reset_campaign(training_signature)

    if st.button("Start / Refresh Training Campaign", type="primary"):
        reset_campaign(training_signature)

    filtered_roster = roster.copy()
    if roster_group_col and group_filter != "All":
        filtered_roster = filtered_roster[
            filtered_roster[roster_group_col].astype(str).str.strip()
            == group_filter
        ]

    rows = []
    for index, row in filtered_roster.iterrows():
        name = clean_text(row[roster_name_col])
        phone_raw = row[roster_phone_col]
        phone, phone_valid = clean_phone(phone_raw)
        group = clean_text(row[roster_group_col]) if roster_group_col else ""

        message = (
            training_template
            .replace("{name}", name)
            .replace("{training_name}", training_name)
            .replace("{date}", training_date.strftime("%d-%m-%Y"))
            .replace("{time}", training_time)
            .replace("{details}", training_mode)
            .replace("{group}", group)
        )

        rows.append({
            "id": f"training_{index}_{training_name}_{training_date}",
            "name": name,
            "employee_id": "",
            "phone_valid": phone_valid,
            "phone_display": clean_text(phone_raw),
            "store": "",
            "group": group,
            "course": training_name,
            "status": "",
            "training_date": (
                f"{training_date.strftime('%d-%m-%Y')} {training_time}".strip()
            ),
            "message": message,
            "url": make_whatsapp_url(phone, message) if phone_valid else ""
        })

    if not training_name.strip():
        st.warning("Enter a training name before starting the campaign.")
        st.stop()

    valid_numbers = sum(1 for row in rows if row["phone_valid"])
    invalid_numbers = len(rows) - valid_numbers

    a, b, c = st.columns(3)
    a.metric("Participants", len(rows))
    b.metric("Valid WhatsApp numbers", valid_numbers)
    c.metric("Number not updated / invalid", invalid_numbers)

    if not rows:
        st.info("No participants found.")
        st.stop()

    campaign_table(rows, "training")
