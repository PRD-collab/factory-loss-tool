import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2

# ---------------- LOGIN ----------------

APP_PASSWORD="1234"

if "authenticated" not in st.session_state:
    st.session_state.authenticated=False

if not st.session_state.authenticated:

    st.title("Factory Loss Tool Login")

    password=st.text_input("Enter PIN",type="password")

    if st.button("Login"):
        if password==APP_PASSWORD:
            st.session_state.authenticated=True
            st.rerun()
        else:
            st.error("Incorrect PIN")

    st.stop()

# ---------------- MACHINES ----------------

machines={
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

conn=psycopg2.connect(
host=st.secrets["DB_HOST"],
port=st.secrets["DB_PORT"],
dbname=st.secrets["DB_NAME"],
user=st.secrets["DB_USER"],
password=st.secrets["DB_PASSWORD"],
sslmode="require"
)

cur=conn.cursor()

# ---------------- SIDEBAR ----------------

menu=st.sidebar.selectbox(
"Module",
[
"Production Entry",
"View Data",
"Modify/Delete Data",
"Pareto Analysis",
"Merge Reasons"
]
)

# =================================================
# PRODUCTION ENTRY
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

                # duplicate prevention
                cur.execute(
                "SELECT COUNT(*) FROM losses WHERE date=%s AND machine=%s AND shift=%s",
                (str(date),machine,shift)
                )

                exists=cur.fetchone()[0]

                if exists>0:
                    st.error(f"Data already exists for {machine} {shift}")
                    st.stop()

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
# LOSS ENTRY
# =================================================

    if "stage" in st.session_state and st.session_state.stage=="loss":

        cases=st.session_state.loss_cases
        idx=st.session_state.case_index

        if idx<len(cases):

            case=cases[idx]

            machine=case["machine"]
            shift=case["shift"]
            gap=case["gap"]

            st.subheader(f"{machine} | {shift} | Loss = {gap}")

            major=st.selectbox("Major Reason",major_reasons)

            cur.execute(
            "SELECT DISTINCT detail_reason FROM losses WHERE machine=%s",
            (machine,)
            )

            existing=[r[0] for r in cur.fetchall()]

            rows=st.session_state.detail_rows

            for i,row in enumerate(rows):

                col1,col2=st.columns([3,1])

                dropdown=col1.selectbox(
                f"Existing Reason {i+1}",
                [""]+existing,
                key=f"d{i}"
                )

                text=col1.text_input(
                f"Or Enter New Reason {i+1}",
                key=f"t{i}"
                )

                reason=dropdown if dropdown else text

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

                        cur.execute(
                        """
                        INSERT INTO losses
                        (date,machine,shift,major_reason,detail_reason,percent,loss_qty)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
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

                    for k in list(st.session_state.keys()):
                        if k.startswith("d") or k.startswith("t") or k.startswith("p"):
                            del st.session_state[k]

                    st.rerun()

        else:

            st.success("All losses recorded")
            st.session_state.stage="entry"

# =================================================
# VIEW DATA
# =================================================

if menu=="View Data":

    st.title("Database Records")

    df=pd.read_sql("SELECT * FROM losses ORDER BY date DESC",conn)

    st.dataframe(df,use_container_width=True)

# =================================================
# MODIFY DELETE
# =================================================

if menu=="Modify/Delete Data":

    st.title("Modify / Delete")

    df=pd.read_sql("SELECT * FROM losses",conn)

    if len(df)==0:
        st.info("No data")
    else:

        date=st.selectbox("Select Date",sorted(df["date"].unique()))

        ddf=df[df["date"]==date]

        st.dataframe(ddf)

        if st.button("Delete This Date"):

            cur.execute("DELETE FROM losses WHERE date=%s",(date,))
            conn.commit()

            st.success("Deleted")

# =================================================
# PARETO
# =================================================

if menu=="Pareto Analysis":

    st.title("Pareto Analysis")

    df=pd.read_sql("SELECT * FROM losses",conn)

    if len(df)==0:
        st.info("No data")

    else:

        df["date"]=pd.to_datetime(df["date"])

        start=st.date_input("Start Date")
        end=st.date_input("End Date")

        df=df[(df["date"]>=pd.to_datetime(start)) & (df["date"]<=pd.to_datetime(end))]

        machine=st.selectbox("Machine",sorted(df["machine"].unique()))

        mdf=df[df["machine"]==machine]

        major=mdf.groupby("major_reason")["loss_qty"].sum().reset_index()

        major=major.sort_values("loss_qty",ascending=False)

        major["cumperc"]=major["loss_qty"].cumsum()/major["loss_qty"].sum()*100

        fig=px.bar(major,x="major_reason",y="loss_qty")

        fig.add_scatter(
        x=major["major_reason"],
        y=major["cumperc"],
        mode="lines+markers",
        yaxis="y2"
        )

        fig.update_layout(
        yaxis2=dict(
        overlaying="y",
        side="right",
        title="Cumulative %"
        )
        )

        st.plotly_chart(fig,use_container_width=True)

        detail=mdf.groupby("detail_reason")["loss_qty"].sum().reset_index()

        fig2=px.bar(detail,x="detail_reason",y="loss_qty")

        st.plotly_chart(fig2,use_container_width=True)

# =================================================
# MERGE
# =================================================

if menu=="Merge Reasons":

    st.title("Merge Reasons")

    df=pd.read_sql("SELECT * FROM losses",conn)

    if len(df)==0:
        st.info("No data")
    else:

        machine=st.selectbox("Machine",sorted(df["machine"].unique()))

        mdf=df[df["machine"]==machine]

        reasons=sorted(mdf["detail_reason"].unique())

        selected=st.multiselect("Reasons",reasons)

        new_name=st.text_input("New Reason")

        if st.button("Merge"):

            for r in selected:

                cur.execute(
                "UPDATE losses SET detail_reason=%s WHERE detail_reason=%s AND machine=%s",
                (new_name,r,machine)
                )

            conn.commit()

            st.success("Merged")