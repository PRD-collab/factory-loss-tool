import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

# ---------------- MACHINES ----------------

machines = {
"AB-1":13000,
"AB-2":13000,
"AB-3":13000,
"Uflex 1":24000,
"Uflex 2":16600,
"Jawala":16600,
"Vffs 2":21500,
"Vffs 3":21500,
"Shruti":18000,
"Blister 1":11800,
"Blister 2":11800
}

shifts=["Shift 1","Shift 2"]

major_reasons=[
"Machine Breakdown",
"Material Not Available",
"Packing Material Not Available",
"Manpower Not Available",
"Efficiency Loss"
]

# ---------------- DATABASE ----------------

import psycopg2
import os

conn = psycopg2.connect(
    host="aws-1-ap-south-1.pooler.supabase.com",
    port=5432,
    dbname="postgres",
    user="postgres",
    password=os.getenv(":BxJDUJ!awJK5UL"),
    sslmode="require"
)
cur = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS losses(
date TEXT,
machine TEXT,
shift TEXT,
major_reason TEXT,
detail_reason TEXT,
percent REAL,
loss_qty REAL
)
""")

conn.commit()

# ---------------- SESSION STATE ----------------

if "stage" not in st.session_state:
    st.session_state.stage="entry"

# ---------------- SIDEBAR ----------------

menu=st.sidebar.selectbox(
"Module",
[
"Production Entry",
"Modify/Delete Data",
"Pareto Analysis",
"Merge Reasons"
]
)

# =================================================
# PRODUCTION ENTRY MATRIX
# =================================================

if menu=="Production Entry":

    st.title("Production Entry")

    date=st.date_input("Select Date")

    rows=[]
    for m in machines:
        for s in shifts:
            rows.append({"Machine":m,"Shift":s,"Actual":0})

    df=pd.DataFrame(rows)

    edited=st.data_editor(df,use_container_width=True)

    if st.button("Submit Production"):

        loss_cases=[]

        for _,row in edited.iterrows():

            machine=row["Machine"]
            shift=row["Shift"]
            actual=row["Actual"]

            target=machines[machine]
            gap=target-actual

            if gap>0:

                loss_cases.append({
                "machine":machine,
                "shift":shift,
                "gap":gap
                })

        st.session_state.loss_cases=loss_cases
        st.session_state.date=str(date)
        st.session_state.case_index=0
        st.session_state.detail_rows=[{"reason":"","percent":100}]
        st.session_state.stage="loss"

        st.rerun()

# =================================================
# LOSS ALLOCATION
# =================================================

    if st.session_state.stage=="loss":

        cases=st.session_state.loss_cases
        idx=st.session_state.case_index

        if idx<len(cases):

            case=cases[idx]

            machine=case["machine"]
            shift=case["shift"]
            gap=case["gap"]

            st.subheader(f"{machine} | {shift} | Loss = {gap}")

            major=st.selectbox("Major Reason",major_reasons,key="major")

            if "detail_rows" not in st.session_state:
                st.session_state.detail_rows=[{"reason":"","percent":100}]

            if st.button("Add Detailed Reason"):
                st.session_state.detail_rows=[{"reason":"","percent":100}]

            rows=st.session_state.detail_rows

            for i,row in enumerate(rows):

                col1,col2=st.columns([3,1])

                reason=col1.text_input(
                f"Detail Reason {i+1}",
                value=row["reason"],
                key=f"r{i}"
                )

                percent=col2.number_input(
                "%",
                min_value=0,
                max_value=100,
                value=row["percent"],
                key=f"p{i}"
                )

                row["reason"]=reason
                row["percent"]=percent

            if st.button("Add Another Reason"):

                rows.append({"reason":"","percent":0})
                st.session_state.detail_rows=rows
                st.rerun()

            total=sum(r["percent"] for r in rows)

            st.write("Total Allocation:",total,"%")

            if total!=100:
                st.warning("Allocation must equal 100%")

            if total==100:

                if st.button("Save & Next"):

                    for r in rows:

                        loss=gap*(r["percent"]/100)

                        c.execute(
                        "INSERT INTO losses VALUES (?,?,?,?,?,?,?)",
                        (
                        st.session_state.date,
                        machine,
                        shift,
                        major,
                        r["reason"] if r["reason"] else "General",
                        r["percent"],
                        loss
                        )
                        )

                    conn.commit()

                    st.session_state.case_index+=1
                    st.session_state.detail_rows=[{"reason":"","percent":100}]
                    st.rerun()

        else:

            st.success("All losses recorded")
            st.session_state.stage="entry"

# =================================================
# MODIFY DELETE
# =================================================

if menu=="Modify/Delete Data":

    st.title("Modify / Delete Data")

    df=pd.read_sql("SELECT * FROM losses",conn)

    if len(df)==0:
        st.info("No data")
    else:

        date=st.selectbox("Select Date",sorted(df["date"].unique()))

        ddf=df[df["date"]==date]

        st.dataframe(ddf,use_container_width=True)

        if st.button("Delete This Date"):

            c.execute("DELETE FROM losses WHERE date=?",(date,))
            conn.commit()

            st.success("Deleted")

# =================================================
# PARETO
# =================================================

if menu=="Pareto Analysis":

    st.title("Machine Pareto")

    df=pd.read_sql("SELECT * FROM losses",conn)

    if len(df)==0:
        st.info("No data")
    else:

        machine=st.selectbox("Machine",sorted(df["machine"].unique()))

        mdf=df[df["machine"]==machine]

        st.subheader("Major Reason Pareto")

        major=mdf.groupby("major_reason")["loss_qty"].sum().reset_index()

        fig=px.bar(major,x="major_reason",y="loss_qty")

        st.plotly_chart(fig,use_container_width=True)

        st.subheader("Detailed Reason Pareto")

        detail=mdf.groupby("detail_reason")["loss_qty"].sum().reset_index()

        fig2=px.bar(detail,x="detail_reason",y="loss_qty")

        st.plotly_chart(fig2,use_container_width=True)

# =================================================
# MACHINE SPECIFIC MERGE
# =================================================

if menu=="Merge Reasons":

    st.title("Merge Reasons")

    df=pd.read_sql("SELECT * FROM losses",conn)

    if len(df)==0:
        st.info("No data")
    else:

        machine=st.selectbox("Select Machine",sorted(df["machine"].unique()))

        mdf=df[df["machine"]==machine]

        reasons=sorted(mdf["detail_reason"].unique())

        selected=st.multiselect("Reasons to Merge",reasons)

        new_name=st.text_input("New Reason Name")

        if st.button("Merge"):

            for r in selected:

                c.execute(
                "UPDATE losses SET detail_reason=? WHERE detail_reason=? AND machine=?",
                (new_name,r,machine)
                )

            conn.commit()

            st.success("Merged successfully")