#!/usr/bin/env python
# coding: utf-8

# In[1]:


import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2 import service_account
import toml
from datetime import datetime
import pandas as pd

# For icon-based sidebar
from streamlit_option_menu import option_menu

# ----------------------------------
# 1) Google Sheets Helper Functions
# ----------------------------------

def init_connection():
    """
    Initializes Google Sheets connection using the service account credentials.
    """
    # Define the scope
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive",
             "https://www.googleapis.com/auth/drive.file"]
    # date = st.secrets("private_key")
    data = toml.load("secrets.toml")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(data, scope)
    client = gspread.authorize(creds)
    return client

    
    # creds = ServiceAccountCredentials.from_json_keyfile_name(".streamlit/secrets.toml", scope)
    # client = gspread.authorize(creds)
    # return client

def get_worksheet(client, sheet_name, worksheet_name):
    """
    Returns a gspread Worksheet object given a client, sheet name, and worksheet name.
    """
    sh = client.open(sheet_name)
    worksheet = sh.worksheet(worksheet_name)
    return worksheet

def find_account_by_id(accounts_ws, user_id):
    """
    Search for an account by ID in the 'accounts' worksheet.
    Returns the row number if found, or None if not found.
    """
    cell = accounts_ws.find(str(user_id))
    if cell:
        return cell.row
    return None

def create_account(accounts_ws, 
                   user_id, name, company, creator_agent, 
                   can_negative_balance):
    """
    Creates a new account in the 'accounts' worksheet. Returns True if successful,
    or False if the account already exists.
    """
    if find_account_by_id(accounts_ws, user_id) is not None:
        return False  # account exists

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row_data = [
        user_id,
        name,
        company,
        creator_agent,
        timestamp,
        str(can_negative_balance),
        "0"  # initial balance is 0
    ]
    accounts_ws.append_row(row_data, value_input_option="USER_ENTERED")
    return True

def record_transaction(transactions_ws, user_id, transaction_type, amount, branch, agent_name):
    """
    Appends a new transaction in the 'transactions' sheet.
    Columns expected (in order):
    1) Timestamp
    2) ID
    3) TransactionType
    4) Amount
    5) Branch
    6) AgentName
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row_data = [
        timestamp,
        user_id,
        transaction_type,
        amount,
        branch,
        agent_name
    ]
    transactions_ws.append_row(row_data, value_input_option="USER_ENTERED")

def update_balance(accounts_ws, row_num, new_balance):
    """
    Updates the user's balance in the 'accounts' sheet (specific row).
    - Column G (7) = CurrentBalance
    """
    accounts_ws.update_cell(row_num, 7, str(new_balance))

def get_account_data(accounts_ws, row_num):
    """
    Returns a dictionary of the account data from a specific row in 'accounts'.
    """
    row_values = accounts_ws.row_values(row_num)
    data = {
        "ID": row_values[0],
        "Name": row_values[1],
        "Company": row_values[2],
        "CreatorAgent": row_values[3],
        "Timestamp": row_values[4],
        "CanHaveNegativeBalance": row_values[5],
        "CurrentBalance": row_values[6],
    }
    return data

def get_transactions_for_id(transactions_ws, user_id):
    """
    Fetch all transactions for a given user_id. Returns a list of dicts.
    The columns in 'transactions' must be:
       Timestamp, ID, TransactionType, Amount, Branch, AgentName
    """
    all_records = transactions_ws.get_all_records()
    user_transactions = []
    for record in all_records:
        if str(record['ID']) == str(user_id):
            user_transactions.append(record)
    return user_transactions

# ----------------------------------
# 2) Streamlit Pages
# ----------------------------------

def page_create_account(accounts_ws):
    st.header("Create New Account")
    with st.form("create_account_form"):
        user_id = st.text_input("ID Number", "")
        name = st.text_input("Name", "")
        company = st.text_input("Company", "")
        creator_agent = st.text_input("Creator Agent", "")
        can_negative_balance = st.checkbox("Can have negative balance?", value=False)
        
        submitted = st.form_submit_button("Create Account")

        if submitted:
            if user_id.strip() == "" or name.strip() == "":
                st.error("Please fill in required fields (ID and Name).")
            else:
                success = create_account(accounts_ws,
                                         user_id,
                                         name,
                                         company,
                                         creator_agent,
                                         can_negative_balance)
                if success:
                    st.success(f"Account for ID {user_id} created successfully!")
                else:
                    st.error(f"Account with ID {user_id} already exists.")

def page_transaction(accounts_ws, transactions_ws):
    st.header("Transaction Recorder")
    with st.form("transaction_form"):
        user_id = st.text_input("ID Number", "")
        transaction_type = st.selectbox("Transaction Type", ["ADD", "DEDUCT"])
        amount = st.number_input("Amount", min_value=0.0, step=1.0)
        
        # New fields
        branch = st.selectbox("Branch", ["Nasser", "Suez", "Arbeen", "Farz"])
        agent_name = st.text_input("Agent Name", "")

        submitted = st.form_submit_button("Record Transaction")

        if submitted:
            if agent_name.strip() == "":
                st.error("Please provide the agent name.")
                return
            
            # 1) Find account row
            row_num = find_account_by_id(accounts_ws, user_id)
            if row_num is None:
                st.error("ID not found. Please create an account first.")
                return

            # 2) Get account data
            account_data = get_account_data(accounts_ws, row_num)
            current_balance = float(account_data["CurrentBalance"])

            # Convert CanHaveNegativeBalance
            raw_can_neg = account_data["CanHaveNegativeBalance"].strip().lower()
            can_negative = (raw_can_neg == "true")

            # 3) Apply transaction logic
            if transaction_type == "ADD":
                new_balance = current_balance + amount
                record_transaction(transactions_ws, user_id, transaction_type, amount, branch, agent_name)
                update_balance(accounts_ws, row_num, new_balance)
                st.success(f"Successfully added {amount} to ID {user_id}. New balance: {new_balance}")

            elif transaction_type == "DEDUCT":
                new_balance = current_balance - amount
                if new_balance < 0 and not can_negative:
                    st.error("This account does not allow negative balance. Transaction rejected.")
                else:
                    record_transaction(transactions_ws, user_id, transaction_type, amount, branch, agent_name)
                    update_balance(accounts_ws, row_num, new_balance)
                    st.success(f"Successfully deducted {amount} from ID {user_id}. New balance: {new_balance}")

def page_search(accounts_ws, transactions_ws):
    st.header("Search Account")
    user_id = st.text_input("Enter ID Number to Search", "")
    if st.button("Search"):
        row_num = find_account_by_id(accounts_ws, user_id)
        if row_num is None:
            st.error("ID not found.")
            return
        
        # --- 1) Get account data
        account_data = get_account_data(accounts_ws, row_num)

        # --- 2) Display account information as a styled table
        st.subheader("Account Information")

        # Convert CurrentBalance to float and format as EGP currency
        current_balance_val = float(account_data["CurrentBalance"])
        balance_str = f"{current_balance_val:,.2f} EGP"  # e.g. "2,722.00 EGP"

        # Create a DataFrame of key-value pairs
        df_info = pd.DataFrame({
            'Parameter': [
                "Name", 
                "Company", 
                "Creator Agent", 
                "Registration Timestamp", 
                "Can Have Negative Balance", 
                "Current Balance"
            ],
            'Value': [
                account_data['Name'],
                account_data['Company'],
                account_data['CreatorAgent'],
                account_data['Timestamp'],
                account_data['CanHaveNegativeBalance'],
                balance_str
            ]
        })

        # Define a function to highlight the Current Balance row (green if positive, red if negative)
        def highlight_balance(value):
            # We'll check if this cell has 'EGP' to identify the Current Balance row
            if "EGP" in value:
                numeric_part = value.replace(' EGP', '').replace(',', '')
                numeric_val = float(numeric_part)
                if numeric_val < 0:
                    return 'color: red; font-weight: bold;'
                else:
                    return 'color: green; font-weight: bold;'
            return ''  # no styling for other cells

        # df_info_styled = df_info.style.applymap(highlight_balance, subset=['Value'])
        df_info_styled = df_info.style.applymap(highlight_balance, subset=[df_info.columns[1]])
        
        # Use .to_html() so the style is preserved in Streamlit
        st.write(df_info_styled.to_html(), unsafe_allow_html=True)

        # --- 3) Display the user’s transactions below
        user_transactions = get_transactions_for_id(transactions_ws, user_id)
        st.subheader("Transaction History")

        if not user_transactions:
            st.write("No transactions found for this ID.")
        else:
            df_transactions = pd.DataFrame(user_transactions)

            # Rename columns for a nicer display
            df_transactions.rename(columns={
                'Timestamp': 'Date & Time',
                'ID': 'User ID',
                'TransactionType': 'Type',
                'Amount': 'Amount',
                'Branch': 'Branch',
                'AgentName': 'Agent Name'
            }, inplace=True)

            st.table(df_transactions)

# ----------------------------------
# 3) Main Streamlit App
# ----------------------------------

def main():
    st.title("Customer Balance & Transactions App")

    # initialize Google Sheets connection
    client = init_connection()

    # open the worksheets
    SHEET_NAME = "database"
    accounts_ws = get_worksheet(client, SHEET_NAME, "accounts")
    transactions_ws = get_worksheet(client, SHEET_NAME, "transactions")

    # --------------------------------------------
    # Sidebar with option_menu (icon-based)
    # --------------------------------------------
    with st.sidebar:
        selected = option_menu(
            menu_title=None,
            options=["Create Account", "Transaction Recorder", "Search Account"],
            icons=["person-plus", "cash-coin", "search"],
            default_index=0
        )
    st.write(f"You selected: {selected}")

    if selected_page == "Create Account":
        page_create_account(accounts_ws)
    elif selected_page == "Transaction Recorder":
        page_transaction(accounts_ws, transactions_ws)
    elif selected_page == "Search Account":
        page_search(accounts_ws, transactions_ws)

if __name__ == "__main__":
    main()
