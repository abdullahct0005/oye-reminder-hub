import streamlit as st
import pandas as pd
import re
from urllib.parse import quote
from datetime import datetime

# ============================================================
# APP CONFIG
# ============================================================

st.set_page_config(
    page_title="OYE Course Reminder Hub",
    page_icon="📚",
    layout="wide"
)

# ============================================================
# CONSTANTS
# ============================================================

BATCH_SIZE = 10

REQUIRED_COLUMNS = [
    "employee's name",
    "Mob No",
    "Trainer Name"
]

FIXED_COLUMNS = {
    "employee's name",
    "Mob No",
    "Store",
    "duties",
    "superior",
    "Entry date",
    "Zone",
    "Location",
    "Active status",
    "Trainer Name",
    "Total Course pending",
    "Total Course Completed",
    "Total Course Enrolled",
    "TYPE"
}

# ============================================================
# FUNCTIONS
# ============================================================

def clean_phone(value):
    """
    Convert mobile number into WhatsApp format.

    Returns:
    - 91XXXXXXXXXX for valid Indian mobile numbers
    - empty string for missing/invalid numbers
    """

    if pd.isna(value):
        return ""

    value_str = str(value).strip()

    if value_str.lower() in [
        "",
        "nan",
        "none",
        "null",
        "n/a",
        "na",
        "0"
    ]:
        return ""

    # Remove .0 from Excel numeric values
    value_str = re.sub(r"\.0$", "", value_str)

    # Keep digits only
    digits = re.sub(r"\D", "", value_str)

    # Indian mobile number without country code
    if len(digits) == 10:
        return "91" + digits

    # Indian mobile number with country code
    if len(digits) == 12 and digits.startswith("91"):
        return digits

    return ""


def phone_display(phone):
    """
    Display phone number in a readable format.
    """

    if not phone:
        return "Number not updated in the system"

    if len(phone) == 12 and phone.startswith("91"):
        return f"+91 {phone[2:]}"

    return f"+{phone}"


def split_name_emp(value):
    """
    Split:
    Vishnu V C-5000580

    Into:
    Vishnu V C
    5000580
    """

    text = str(value).strip()

    if text.lower() in ["nan", "none", ""]:
        return "", ""

    match = re.search(r"-(\d{5,})$", text)

    if match:
        name = text[:match.start()].strip()
        employee_id = match.group(1)

        return name, employee_id

    return text, ""


def course_columns(df):
    """
    Identify course columns by removing fixed report columns.
    """

    return [
        column
        for column in df.columns
        if column not in FIXED_COLUMNS
    ]


def normalize_status(value):
    """
    Normalize course status.
    """

    if pd.isna(value):
        return "Not started"

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null"]:
        return "Not started"

    return text


def status_class(value):
    """
    Completed or Pending.
    """

    status = normalize_status(value).lower()

    if status in [
        "completed",
        "complete",
        "100%",
        "100"
    ]:
        return "Completed"

    return "Pending"


def build_message(
    name,
    course,
    status,
    reminder_level,
    custom_template=""
):
    """
    Create personalized WhatsApp message.
    """

    name = str(name).strip()
    course = str(course).strip()
    status = str(status).strip()

    if custom_template.strip():

        return (
            custom_template
            .replace("{name}", name)
            .replace("{course}", course)
            .replace("{status}", status)
        )

    if reminder_level == "First Reminder":

        return (
            f"Hi {name}, your *{course}* course on OYE "
            f"is currently showing as *{status}*. "
            f"Please complete the course as soon as possible. "
            f"This is mandatory."
        )

    if reminder_level == "Second Reminder":

        return (
            f"Hi {name}, your *{course}* course is still "
            f"showing as *{status}* on OYE. "
            f"Please complete the mandatory course immediately."
        )

    return (
        f"URGENT REMINDER: Hi {name}, your *{course}* "
        f"course is still pending on OYE. "
        f"Please complete it immediately."
    )


@st.cache_data(show_spinner=False)
def load_report(file_bytes):
    """
    Load Excel from uploaded file bytes.
    """

    return pd.read_excel(file_bytes)


def initialize_campaign(campaign_key, total_count):
    """
    Initialize or reset campaign state.
    """

    if (
        "campaign_state" not in st.session_state
        or st.session_state.campaign_state.get("key") != campaign_key
    ):

        st.session_state.campaign_state = {
            "key": campaign_key,
            "batch_index": 0,
            "sent": set(),
            "skipped": set(),
            "started": False,
            "started_at": None,
            "total_count": total_count
        }


def mark_batch_as_sent(state, batch_indices, valid_indices):
    """
    Mark all valid-number OECs in the current batch as sent.
    Missing-number OECs are not marked as sent.
    """

    for index in valid_indices:
        state["sent"].add(index)


def whatsapp_url(phone, message):
    """
    Create WhatsApp Web URL.
    """

    return (
        f"https://web.whatsapp.com/send"
        f"?phone={phone}"
        f"&text={quote(message)}"
    )


def whatsapp_button_html(phone, message):
    """
    Create an HTML button that always uses the same
    browser window/tab name: whatsapp_chat.

    This prevents a new WhatsApp tab from being created
    for every OEC.
    """

    url = whatsapp_url(phone, message)

    return f"""
    <a
        href="{url}"
        target="whatsapp_chat"
        style="
            display: inline-block;
            width: 100%;
            box-sizing: border-box;
            padding: 10px 16px;
            background-color: #25D366;
            color: white !important;
            text-align: center;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            font-size: 15px;
        "
    >
        Open WhatsApp Chat
    </a>
    """


# ============================================================
# HEADER
# ============================================================

st.title("OYE Course Reminder Hub")

st.caption(
    "Shared trainer dashboard • "
    "Upload OYE report • "
    "Select trainer • "
    "Send personalized WhatsApp reminders in batches"
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("Admin / Report")

    uploaded = st.file_uploader(
        "Upload latest OYE Excel",
        type=["xlsx", "xls"]
    )

    st.caption(
        "Upload the newest report whenever OYE "
        "completion status changes."
    )

    st.divider()

    st.header("How trainers use it")

    st.markdown(
        "1. Upload latest report\n"
        "2. Select your name\n"
        "3. Select course\n"
        "4. Start campaign\n"
        "5. Send reminders in batches of 10\n"
        "6. Mark each OEC as sent\n"
        "7. Move to next 10"
    )

    st.divider()

    st.header("Number Status")

    st.caption(
        "If the OYE report does not contain a valid "
        "mobile number, the app shows:\n\n"
        "**Number not updated in the system**"
    )


# ============================================================
# FILE VALIDATION
# ============================================================

if not uploaded:

    st.info(
        "Upload the latest OYE Excel report from "
        "the left panel to start."
    )

    st.stop()


try:

    file_bytes = uploaded.getvalue()

    raw = load_report(file_bytes)

except Exception as error:

    st.error(
        f"Could not read the Excel file: {error}"
    )

    st.stop()


# Remove spaces from column names
raw.columns = [
    str(column).strip()
    for column in raw.columns
]


missing_columns = [
    column
    for column in REQUIRED_COLUMNS
    if column not in raw.columns
]


if missing_columns:

    st.error(
        "Missing required columns: "
        + ", ".join(missing_columns)
    )

    st.stop()


courses = course_columns(raw)


if not courses:

    st.error(
        "No OYE course columns were detected."
    )

    st.stop()


trainers = sorted(
    raw["Trainer Name"]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)


if not trainers:

    st.error(
        "No trainer names were found in the report."
    )

    st.stop()


# ============================================================
# SETTINGS
# ============================================================

col1, col2, col3 = st.columns(3)


with col1:

    trainer = st.selectbox(
        "Select Your Trainer Name",
        trainers
    )


with col2:

    course = st.selectbox(
        "Select Course",
        courses
    )


with col3:

    reminder_level = st.selectbox(
        "Reminder Type",
        [
            "First Reminder",
            "Second Reminder",
            "Final / Urgent Reminder"
        ]
    )


custom_template = st.text_area(
    "Optional custom message template",
    placeholder=(
        "Example:\n"
        "Hi {name}, your {course} course is currently "
        "showing as {status}. Please complete it today."
    ),
    height=100
)


st.caption(
    "Available message variables: "
    "{name}, {course}, {status}"
)


# ============================================================
# PREPARE TRAINER DATA
# ============================================================

data = raw[
    raw["Trainer Name"]
    .astype(str)
    .str.strip()
    .eq(trainer)
].copy()


data[[
    "OEC Name",
    "Employee ID"
]] = data["employee's name"].apply(
    lambda value: pd.Series(
        split_name_emp(value)
    )
)


data["WhatsApp Phone"] = (
    data["Mob No"]
    .apply(clean_phone)
)


data["Phone Status"] = data[
    "WhatsApp Phone"
].apply(
    lambda value: (
        "Number Available"
        if value
        else "Number not updated in the system"
    )
)


data["Course Status"] = data[
    course
].apply(
    normalize_status
)


data["Campaign Status"] = data[
    "Course Status"
].apply(
    status_class
)


data["Reminder Message"] = data.apply(
    lambda row: build_message(
        name=row["OEC Name"],
        course=course,
        status=row["Course Status"],
        reminder_level=reminder_level,
        custom_template=custom_template
    ),
    axis=1
)


pending = data[
    data["Campaign Status"] == "Pending"
].reset_index(drop=True)


completed = data[
    data["Campaign Status"] == "Completed"
].reset_index(drop=True)


# ============================================================
# CAMPAIGN STATE
# ============================================================

campaign_key = (
    f"{uploaded.name}|"
    f"{trainer}|"
    f"{course}|"
    f"{reminder_level}|"
    f"{custom_template}|"
    f"{len(pending)}"
)


initialize_campaign(
    campaign_key,
    len(pending)
)


state = st.session_state.campaign_state


# ============================================================
# METRICS
# ============================================================

total_oecs = len(data)
pending_count = len(pending)
completed_count = len(completed)

missing_number_count = len(
    pending[
        pending["WhatsApp Phone"] == ""
    ]
)


metric1, metric2, metric3, metric4 = st.columns(4)


metric1.metric(
    "My Total OECs",
    total_oecs
)


metric2.metric(
    "Pending",
    pending_count
)


metric3.metric(
    "Completed",
    completed_count
)


completion_percentage = (
    completed_count / total_oecs * 100
    if total_oecs
    else 0
)


metric4.metric(
    "Completion %",
    f"{completion_percentage:.1f}%"
)


if missing_number_count > 0:

    st.warning(
        f"⚠ {missing_number_count} pending OEC(s) have "
        f"no valid mobile number in the OYE report."
    )


# ============================================================
# CHANNEL / TYPE SUMMARY
# ============================================================

if "TYPE" in data.columns:

    with st.expander("View channel/type summary"):

        summary = (
            data
            .groupby("TYPE", dropna=False)
            .agg(
                Total=("OEC Name", "size"),
                Pending=(
                    "Campaign Status",
                    lambda values:
                        (values == "Pending").sum()
                ),
                Completed=(
                    "Campaign Status",
                    lambda values:
                        (values == "Completed").sum()
                )
            )
            .reset_index()
        )

        st.dataframe(
            summary,
            use_container_width=True,
            hide_index=True
        )


st.divider()


# ============================================================
# CAMPAIGN SECTION
# ============================================================

st.subheader(
    "My WhatsApp Reminder Campaign"
)


if pending_count == 0:

    st.success(
        "🎉 No pending OECs for this course "
        "in the latest report."
    )


else:

    # --------------------------------------------------------
    # CAMPAIGN START
    # --------------------------------------------------------

    top1, top2, top3, top4 = st.columns(
        [1.3, 1, 1.5, 1]
    )


    with top1:

        if not state["started"]:

            if st.button(
                "Start Campaign",
                type="primary",
                use_container_width=True
            ):

                state["started"] = True

                state["started_at"] = (
                    datetime.now().strftime(
                        "%d-%m-%Y %I:%M %p"
                    )
                )

                st.rerun()

        else:

            st.success("Campaign Active")


    with top2:

        st.metric(
            "Marked Sent",
            len(state["sent"])
        )


    with top3:

        if state["started_at"]:

            st.caption(
                f"Started: "
                f"{state['started_at']}"
            )


    with top4:

        total_batches = (
            (pending_count + BATCH_SIZE - 1)
            // BATCH_SIZE
        )

        st.metric(
            "Current Batch",
            f"{state['batch_index'] + 1} "
            f"of {total_batches}"
        )


    # --------------------------------------------------------
    # PROGRESS
    # --------------------------------------------------------

    sent_count = len(state["sent"])

    progress = (
        sent_count / pending_count
        if pending_count
        else 0
    )

    st.progress(progress)

    st.caption(
        f"{sent_count} of {pending_count} "
        f"pending OECs marked as sent"
    )


    # --------------------------------------------------------
    # CURRENT BATCH
    # --------------------------------------------------------

    batch_start = (
        state["batch_index"]
        * BATCH_SIZE
    )


    batch_end = min(
        batch_start + BATCH_SIZE,
        pending_count
    )


    batch = pending.iloc[
        batch_start:batch_end
    ].copy()


    st.markdown(
        f"### Batch {state['batch_index'] + 1}: "
        f"OEC {batch_start + 1}–{batch_end} "
        f"of {pending_count}"
    )


    # --------------------------------------------------------
    # COMPLETED CAMPAIGN
    # --------------------------------------------------------

    if (
        sent_count >= pending_count
        and pending_count > 0
    ):

        st.success(
            "🎉 Campaign Completed!"
        )

        st.markdown(
            f"""
            ### Final Campaign Summary

            **Total Pending OECs:** {pending_count}

            **Marked Sent:** {sent_count}

            **Missing / Invalid Numbers:** 
            {missing_number_count}
            """
        )


    # --------------------------------------------------------
    # SHOW BATCH
    # --------------------------------------------------------

    else:

        if not state["started"]:

            st.info(
                "Click Start Campaign to begin sending "
                "WhatsApp reminders."
            )


        # ----------------------------------------------------
        # EACH OEC CARD
        # ----------------------------------------------------

        for position, (
            original_index,
            row
        ) in enumerate(
            batch.iterrows(),
            start=batch_start + 1
        ):

            is_sent = (
                original_index
                in state["sent"]
            )

            has_valid_number = (
                bool(row["WhatsApp Phone"])
            )


            # OEC heading
            if is_sent:

                st.success(
                    f"✓ {position}. "
                    f"{row['OEC Name']} "
                    f"— Marked Sent"
                )

            elif not has_valid_number:

                st.warning(
                    f"⚠ {position}. "
                    f"{row['OEC Name']} "
                    f"— Number not updated in the system"
                )

            else:

                st.markdown(
                    f"### {position}. "
                    f"{row['OEC Name']}"
                )


            # Information
            info1, info2, info3, info4 = st.columns(4)


            with info1:

                st.write(
                    f"**Phone:** "
                    f"{phone_display(row['WhatsApp Phone'])}"
                )


            with info2:

                st.write(
                    f"**Store:** "
                    f"{row.get('Store', '')}"
                )


            with info3:

                st.write(
                    f"**Type:** "
                    f"{row.get('TYPE', '')}"
                )


            with info4:

                st.write(
                    f"**OYE Status:** "
                    f"{row['Course Status']}"
                )


            # ------------------------------------------------
            # MISSING NUMBER
            # ------------------------------------------------

            if not has_valid_number:

                st.error(
                    "Number not updated in the system. "
                    "Please update the mobile number in "
                    "the OYE report/system before sending."
                )

                st.divider()

                continue


            # ------------------------------------------------
            # MESSAGE
            # ------------------------------------------------

            message = st.text_area(
                "Personalized Message",
                value=row["Reminder Message"],
                height=90,
                key=(
                    f"message_"
                    f"{campaign_key}_"
                    f"{original_index}"
                )
            )


            # ------------------------------------------------
            # WHATSAPP + SENT BUTTON
            # ------------------------------------------------

            button_col1, button_col2 = st.columns(
                [2, 1]
            )


            with button_col1:

                if state["started"]:

                    # Same named WhatsApp window/tab
                    st.markdown(
                        whatsapp_button_html(
                            row["WhatsApp Phone"],
                            message
                        ),
                        unsafe_allow_html=True
                    )

                    st.caption(
                        "The app attempts to reuse the same "
                        "WhatsApp browser tab named "
                        "'whatsapp_chat'."
                    )

                else:

                    st.button(
                        "Open WhatsApp Chat",
                        disabled=True,
                        key=(
                            f"disabled_whatsapp_"
                            f"{original_index}"
                        ),
                        use_container_width=True
                    )


            with button_col2:

                if is_sent:

                    st.button(
                        "✓ Sent",
                        disabled=True,
                        key=(
                            f"sent_done_"
                            f"{original_index}"
                        ),
                        use_container_width=True
                    )

                else:

                    if st.button(
                        "Mark Sent",
                        disabled=not state["started"],
                        key=(
                            f"mark_sent_"
                            f"{original_index}"
                        ),
                        use_container_width=True
                    ):

                        state["sent"].add(
                            original_index
                        )

                        st.rerun()


            st.divider()


        # ----------------------------------------------------
        # BATCH ACTIONS
        # ----------------------------------------------------

        st.markdown(
            "### Batch Actions"
        )


        current_batch_indices = list(
            range(batch_start, batch_end)
        )


        valid_batch_indices = [
            index
            for index in current_batch_indices
            if pending.loc[
                index,
                "WhatsApp Phone"
            ]
        ]


        sent_in_batch = sum(
            1
            for index in current_batch_indices
            if index in state["sent"]
        )


        valid_in_batch = len(
            valid_batch_indices
        )


        batch_action1, batch_action2, batch_action3, batch_action4 = st.columns(
            4
        )


        with batch_action1:

            if st.button(
                "← Previous 10",
                disabled=(
                    state["batch_index"] == 0
                ),
                use_container_width=True
            ):

                state["batch_index"] -= 1

                st.rerun()


        with batch_action2:

            if st.button(
                "Mark All Valid Numbers Sent",
                disabled=not state["started"],
                use_container_width=True
            ):

                mark_batch_as_sent(
                    state,
                    current_batch_indices,
                    valid_batch_indices
                )

                st.rerun()


        with batch_action3:

            batch_has_unsent_valid = any(
                index not in state["sent"]
                for index in valid_batch_indices
            )


            next_disabled = (
                batch_has_unsent_valid
                or batch_end >= pending_count
            )


            if st.button(
                "Next 10 →",
                disabled=next_disabled,
                use_container_width=True
            ):

                state["batch_index"] += 1

                st.rerun()


        with batch_action4:

            if st.button(
                "Reset Campaign",
                use_container_width=True
            ):

                st.session_state.campaign_state = {
                    "key": campaign_key,
                    "batch_index": 0,
                    "sent": set(),
                    "skipped": set(),
                    "started": False,
                    "started_at": None,
                    "total_count": pending_count
                }

                st.rerun()


        # ----------------------------------------------------
        # BATCH STATUS
        # ----------------------------------------------------

        st.caption(
            f"Current batch: "
            f"{sent_in_batch} of {valid_in_batch} "
            f"valid-number OECs marked as sent."
        )


        if missing_number_count > 0:

            st.caption(
                "OECs with missing numbers are not counted "
                "as sent and remain highlighted for follow-up."
            )


st.divider()


# ============================================================
# PENDING QUEUE
# ============================================================

st.subheader(
    "My Pending Queue"
)


queue = pending.copy()


queue["Session Status"] = [

    (
        "Marked Sent"
        if index in state["sent"]

        else (
            "Number not updated in the system"
            if not queue.loc[
                index,
                "WhatsApp Phone"
            ]
            else "Pending Send"
        )
    )

    for index in queue.index
]


queue["WhatsApp Phone"] = queue[
    "WhatsApp Phone"
].apply(
    phone_display
)


queue_columns = [
    "OEC Name",
    "Employee ID",
    "WhatsApp Phone",
    "Phone Status",
    "Store",
    "TYPE",
    "Course Status",
    "Session Status",
    "Reminder Message"
]


available_columns = [
    column
    for column in queue_columns
    if column in queue.columns
]


st.dataframe(
    queue[available_columns],
    use_container_width=True,
    height=450
)


# ============================================================
# DOWNLOAD CAMPAIGN REPORT
# ============================================================

st.download_button(
    "Download Full Campaign Report (CSV)",
    queue[
        available_columns
    ].to_csv(
        index=False
    ).encode(
        "utf-8-sig"
    ),
    file_name=(
        f"OYE_Campaign_"
        f"{trainer.replace(' ', '_')}_"
        f"{course.replace(' ', '_')}.csv"
    ),
    mime="text/csv"
)


# ============================================================
# FOOTER
# ============================================================

st.divider()


st.caption(
    "OYE Course Reminder Hub • "
    "Batch-based personalized WhatsApp reminder system • "
    "Current campaign status is stored in the active browser session."
)


st.caption(
    "For permanent shared history, trainer logins, "
    "and campaign tracking across devices, "
    "the next version can be connected to "
    "Supabase or Firebase."
)
