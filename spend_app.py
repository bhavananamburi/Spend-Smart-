import os
from datetime import date

import mysql.connector
import pandas as pd
import streamlit as st

# ---------- PAGE CONFIGURATION ----------
st.set_page_config(
    page_title="SpendSmart | Expense Tracker",
    page_icon="💰",
    layout="wide"
)

DEMO_USER_ID = 1

# ---------- DATABASE CONNECTION ----------
def get_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv(
            "MYSQL_DATABASE", "spendsmart_project_db"
        )
    )

# ---------- LOAD DATA ----------
def load_categories():
    connection = get_connection()
    try:
        return pd.read_sql(
            """
            SELECT category_id, category_name, category_type
            FROM spend_categories
            ORDER BY category_name
            """,
            connection
        )
    finally:
        connection.close()

def load_transactions():
    connection = get_connection()
    try:
        return pd.read_sql(
            """
            SELECT t.transaction_id, t.transaction_date,
                   t.transaction_type, c.category_name,
                   t.amount, t.description
            FROM spend_transactions t
            JOIN spend_categories c
                ON t.category_id = c.category_id
            WHERE t.user_id = %s
            ORDER BY t.transaction_date DESC,
                     t.transaction_id DESC
            """,
            connection,
            params=(DEMO_USER_ID,)
        )
    finally:
        connection.close()

def load_budgets(month_start):
    connection = get_connection()
    try:
        return pd.read_sql(
            """
            SELECT b.budget_id, b.category_id,
                   c.category_name, b.budget_amount
            FROM spend_budgets b
            JOIN spend_categories c
                ON b.category_id = c.category_id
            WHERE b.user_id = %s AND b.month_start = %s
            ORDER BY c.category_name
            """,
            connection,
            params=(DEMO_USER_ID, month_start)
        )
    finally:
        connection.close()

# ---------- SAVE TRANSACTION ----------
def save_transaction(
    category_id, kind, amount, description, transaction_date
):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO spend_transactions
            (user_id, category_id, transaction_type,
             amount, description, transaction_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                DEMO_USER_ID,
                category_id,
                kind,
                amount,
                description,
                transaction_date
            )
        )
        connection.commit()
    finally:
        connection.close()

# ---------- SAVE OR UPDATE BUDGET ----------
def save_budget(category_id, month_start, amount):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO spend_budgets
            (user_id, category_id, month_start, budget_amount)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                budget_amount = VALUES(budget_amount)
            """,
            (
                DEMO_USER_ID, category_id,
                month_start, amount
            )
        )
        connection.commit()
    finally:
        connection.close()

# ---------- DELETE TRANSACTION ----------
def delete_transaction(transaction_id):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            DELETE FROM spend_transactions
            WHERE transaction_id = %s AND user_id = %s
            """,
            (transaction_id, DEMO_USER_ID)
        )
        connection.commit()
    finally:
        connection.close()

# ---------- WEBSITE HEADER ----------
st.title("💰 SpendSmart")
st.subheader("Personal Finance & Expense Tracker")
st.caption(
    "Track your money. Manage your budget. "
    "Make smarter spending decisions."
)

# ---------- SIDEBAR NAVIGATION ----------
page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Add Transaction",
        "Manage Budgets",
        "Transaction History"
    ]
)

# ---------- CONNECT TO DATABASE ----------
try:
    categories = load_categories()
    transactions = load_transactions()
except mysql.connector.Error as error:
    st.error(
        "Unable to connect to the SpendSmart database. "
        "Check your MySQL service, database tables, and "
        "connection settings."
    )
    st.code(str(error))
    st.stop()

# ---------- SELECT MONTH ----------
today = date.today()
first_day = today.replace(day=1)

selected_date = st.sidebar.date_input(
    "Choose a month",
    value=first_day,
    help="Choose any date in the month you want to view."
)
month_start = selected_date.replace(day=1)

if month_start.month == 12:
    next_month = date(month_start.year + 1, 1, 1)
else:
    next_month = date(
        month_start.year, month_start.month + 1, 1
    )

# ---------- FILTER CURRENT MONTH ----------
month_transactions = transactions.copy()

if not month_transactions.empty:
    month_transactions["transaction_date"] = pd.to_datetime(
        month_transactions["transaction_date"]
    )

    month_transactions = month_transactions[
        (
            month_transactions["transaction_date"]
            >= pd.Timestamp(month_start)
        )
        & (
            month_transactions["transaction_date"]
            < pd.Timestamp(next_month)
        )
    ]

if month_transactions.empty:
    total_income = 0.0
    total_expenses = 0.0
else:
    income_rows = month_transactions[
        month_transactions["transaction_type"] == "Income"
    ]
    expense_rows = month_transactions[
        month_transactions["transaction_type"] == "Expense"
    ]

    total_income = float(income_rows["amount"].sum())
    total_expenses = float(expense_rows["amount"].sum())

balance = total_income - total_expenses

# ==================================================
# PAGE 1: DASHBOARD
# ==================================================
if page == "Dashboard":
    st.header("Monthly Financial Dashboard")
    st.caption(month_start.strftime("%B %Y"))

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Income", f"₹{total_income:,.2f}")
    col2.metric("Total Expenses", f"₹{total_expenses:,.2f}")
    col3.metric("Remaining Balance", f"₹{balance:,.2f}")
    col4.metric("Transactions", len(month_transactions))

    st.divider()

    left, right = st.columns(2)

    # Expenses by category
    with left:
        st.subheader("Expenses by Category")

        expense_data = month_transactions[
            month_transactions["transaction_type"] == "Expense"
        ]

        if expense_data.empty:
            st.info("Add expenses to display this chart.")
        else:
            category_totals = (
                expense_data.groupby("category_name")["amount"]
                .sum()
                .sort_values(ascending=False)
            )
            st.bar_chart(category_totals)

    # Income versus expenses
    with right:
        st.subheader("Income vs Expenses")

        comparison = pd.DataFrame(
            {
                "Type": ["Income", "Expenses"],
                "Amount": [total_income, total_expenses]
            }
        ).set_index("Type")

        st.bar_chart(comparison)

    # Monthly budget alerts
    st.divider()
    st.subheader("Monthly Budget Alerts")

    try:
        budgets = load_budgets(month_start)
    except mysql.connector.Error:
        budgets = pd.DataFrame()
        st.error("Unable to load monthly budgets.")

    if budgets.empty:
        st.info(
            "No budgets set for this month. "
            "Open Manage Budgets to create one."
        )
    else:
        for _, budget in budgets.iterrows():
            category = budget["category_name"]
            limit = float(budget["budget_amount"])

            matching = month_transactions[
                (
                    month_transactions["transaction_type"]
                    == "Expense"
                )
                & (
                    month_transactions["category_name"]
                    == category
                )
            ]

            spent = (
                float(matching["amount"].sum())
                if not matching.empty else 0.0
            )

            ratio = spent / limit if limit > 0 else 0.0

            st.write(
                f"**{category}** — ₹{spent:,.2f} "
                f"spent out of ₹{limit:,.2f}"
            )

            st.progress(min(ratio, 1.0))

            if spent > limit:
                st.error(
                    f"{category}: budget exceeded by "
                    f"₹{spent - limit:,.2f}."
                )
            elif ratio >= 0.8:
                st.warning(
                    f"{category}: {ratio * 100:.0f}% "
                    "of the budget has been used."
                )
            else:
                st.success("Spending is within budget.")

    st.divider()
    st.subheader("Recent Transactions")

    if month_transactions.empty:
        st.info("No transactions recorded for this month.")
    else:
        st.dataframe(
            month_transactions.head(10),
            use_container_width=True,
            hide_index=True
        )

# ==================================================
# PAGE 2: ADD TRANSACTION
# ==================================================
elif page == "Add Transaction":
    st.header("Add Income or Expense")

    kind = st.radio(
        "Transaction type",
        ["Expense", "Income"],
        horizontal=True
    )

    available_categories = categories[
        categories["category_type"] == kind
    ]

    with st.form("spend_transaction_form", clear_on_submit=True):
        category_name = st.selectbox(
            "Category",
            available_categories["category_name"].tolist()
        )

        amount = st.number_input(
            "Amount (₹)",
            min_value=0.01,
            value=100.0,
            step=50.0
        )

        transaction_date = st.date_input(
            "Transaction date",
            value=today
        )

        description = st.text_input(
            "Description",
            placeholder="Example: Lunch, bus fare, salary"
        )

        submitted = st.form_submit_button("Save Transaction")

        if submitted:
            selected_category = available_categories[
                available_categories["category_name"]
                == category_name
            ].iloc[0]

            try:
                save_transaction(
                    int(selected_category["category_id"]),
                    kind,
                    amount,
                    description.strip(),
                    transaction_date
                )
                st.success("Transaction saved successfully!")
                st.rerun()
            except mysql.connector.Error as error:
                st.error("Unable to save transaction.")
                st.code(str(error))

# ==================================================
# PAGE 3: MANAGE BUDGETS
# ==================================================
elif page == "Manage Budgets":
    st.header("Manage Monthly Budgets")
    st.write(
        "Set a spending limit for each expense category "
        "and month."
    )
    st.caption(
        f"Selected month: {month_start.strftime('%B %Y')}"
    )

    expense_categories = categories[
        categories["category_type"] == "Expense"
    ]

    with st.form("spend_budget_form"):
        category_name = st.selectbox(
            "Expense category",
            expense_categories["category_name"].tolist()
        )

        budget_amount = st.number_input(
            "Monthly budget (₹)",
            min_value=1.0,
            value=2000.0,
            step=100.0
        )

        submitted = st.form_submit_button("Save Budget")

        if submitted:
            selected_category = expense_categories[
                expense_categories["category_name"]
                == category_name
            ].iloc[0]

            try:
                save_budget(
                    int(selected_category["category_id"]),
                    month_start,
                    budget_amount
                )
                st.success(
                    "Budget saved or updated successfully!"
                )
                st.rerun()
            except mysql.connector.Error as error:
                st.error("Unable to save budget.")
                st.code(str(error))

    st.divider()
    st.subheader("Saved Budgets")

    try:
        budgets = load_budgets(month_start)

        if budgets.empty:
            st.info("No budgets have been set for this month.")
        else:
            display_budgets = budgets[
                ["category_name", "budget_amount"]
            ].rename(
                columns={
                    "category_name": "Category",
                    "budget_amount": "Monthly Limit (₹)"
                }
            )

            st.dataframe(
                display_budgets,
                use_container_width=True,
                hide_index=True
            )
    except mysql.connector.Error as error:
        st.error("Unable to display saved budgets.")
        st.code(str(error))

# ==================================================
# PAGE 4: TRANSACTION HISTORY
# ==================================================
elif page == "Transaction History":
    st.header("Transaction History")

    if transactions.empty:
        st.info("No transactions recorded yet.")
    else:
        search = st.text_input(
            "Search by category or description"
        )

        type_filter = st.selectbox(
            "Filter transaction type",
            ["All", "Income", "Expense"]
        )

        filtered = transactions.copy()

        if search.strip():
            matching_text = (
                filtered["category_name"].str.contains(
                    search, case=False, na=False
                )
                | filtered["description"].fillna("").str.contains(
                    search, case=False, na=False
                )
            )
            filtered = filtered[matching_text]

        if type_filter != "All":
            filtered = filtered[
                filtered["transaction_type"] == type_filter
            ]

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Download Transactions as CSV",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name="spendsmart_transactions.csv",
            mime="text/csv"
        )

        st.divider()
        st.subheader("Delete a Transaction")

        transaction_ids = filtered["transaction_id"].tolist()

        if transaction_ids:
            selected_id = st.selectbox(
                "Select transaction ID to delete",
                transaction_ids
            )

            confirm_delete = st.checkbox(
                "I confirm that I want to delete this transaction."
            )

            if st.button("Delete Selected Transaction"):
                if not confirm_delete:
                    st.warning(
                        "Please confirm before deleting."
                    )
                else:
                    try:
                        delete_transaction(int(selected_id))
                        st.success("Transaction deleted successfully.")
                        st.rerun()
                    except mysql.connector.Error as error:
                        st.error("Unable to delete transaction.")
                        st.code(str(error))

# ---------- FOOTER ----------
st.sidebar.divider()
st.sidebar.caption(
    "SpendSmart Project | Personal Finance Dashboard"
)