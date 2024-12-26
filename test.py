#!/usr/bin/env python
# coding: utf-8

# In[1]:


import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd

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
    
    creds = ServiceAccountCredentials.from_json_keyfile_name("t.json", scope)
    client = gspread.authorize(creds)
    return client

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
    # We assume the ID column is the first column
    # .find() returns a cell object if found
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
    # Check if ID already exists
    if find_account_by_id(accounts_ws, user_id) is not None:
        return False  # account exists

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Prepare row data; must match the columns in the 'accounts' sheet
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

def record_transaction(transactions_ws, user_id, transaction_type, amount):
    """
    Appends a new transaction in the 'transactions' sheet.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row_data = [
        timestamp,
        user_id,
        transaction_type,
        amount
    ]
    transactions_ws.append_row(row_data, value_input_option="USER_ENTERED")

def update_balance(accounts_ws, row_num, new_balance):
    """
    Updates the user's balance in the 'accounts' sheet (specific row).
    """
    # CurrentBalance is column G (7) if we follow the example columns:
    #  1=ID, 2=Name, 3=Company, 4=CreatorAgent, 5=Timestamp, 
    #  6=CanHaveNegativeBalance, 7=CurrentBalance
    accounts_ws.update_cell(row_num, 7, str(new_balance))

def get_account_data(accounts_ws, row_num):
    """
    Returns a dictionary of the account data from a specific row in 'accounts'.
    """
    # read the entire row
    row_values = accounts_ws.row_values(row_num)
    # Make sure row_values matches the columns:
    # row_values = [ID, Name, Company, CreatorAgent, Timestamp, CanHaveNegativeBalance, CurrentBalance]
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
    """
    # First, get all values in the transactions sheet
    all_records = transactions_ws.get_all_records()
    # each record is a dict with keys matching the columns
    # columns are: Timestamp, ID, TransactionType, Amount
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
        submitted = st.form_submit_button("Record Transaction")

        if submitted:
            # 1) Find account row
            row_num = find_account_by_id(accounts_ws, user_id)
            if row_num is None:
                st.error("ID not found. Please create an account first.")
                return

            # 2) Get account data
            account_data = get_account_data(accounts_ws, row_num)
            current_balance = float(account_data["CurrentBalance"])

            # Updated: Convert the string to a proper boolean, ignoring case:
            raw_can_neg = account_data["CanHaveNegativeBalance"].strip().lower()
            can_negative = (raw_can_neg == "true")

            # 3) Apply transaction logic
            if transaction_type == "ADD":
                new_balance = current_balance + amount
                record_transaction(transactions_ws, user_id, transaction_type, amount)
                update_balance(accounts_ws, row_num, new_balance)
                st.success(f"Successfully added {amount} to ID {user_id}. New balance: {new_balance}")

            elif transaction_type == "DEDUCT":
                new_balance = current_balance - amount
                # If new balance is < 0 and the account does NOT allow negative, reject.
                if new_balance < 0 and not can_negative:
                    st.error("This account does not allow negative balance. Transaction rejected.")
                else:
                    record_transaction(transactions_ws, user_id, transaction_type, amount)
                    update_balance(accounts_ws, row_num, new_balance)
                    st.success(f"Successfully deducted {amount} from ID {user_id}. New balance: {new_balance}")

# def page_search(accounts_ws, transactions_ws):
#     st.header("Search Account")
#     user_id = st.text_input("Enter ID Number to Search", "")
#     if st.button("Search"):
#         row_num = find_account_by_id(accounts_ws, user_id)
#         if row_num is None:
#             st.error("ID not found.")
#             return
        
#         # Get account data
#         account_data = get_account_data(accounts_ws, row_num)
#         st.subheader("Account Information")
#         st.write(f"**Name:** {account_data['Name']}")
#         st.write(f"**Company:** {account_data['Company']}")
#         st.write(f"**Creator Agent:** {account_data['CreatorAgent']}")
#         st.write(f"**Registration Timestamp:** {account_data['Timestamp']}")
#         st.write(f"**Can Have Negative Balance:** {account_data['CanHaveNegativeBalance']}")
#         st.write(f"**Current Balance:** {account_data['CurrentBalance']}")

#         # Get transactions
#         user_transactions = get_transactions_for_id(transactions_ws, user_id)
#         st.subheader("Transaction History")
#         if not user_transactions:
#             st.write("No transactions found for this ID.")
#         else:
#             for tx in user_transactions:
#                 st.write(f"- **Timestamp**: {tx['Timestamp']}, "
#                          f"**Type**: {tx['TransactionType']}, "
#                          f"**Amount**: {tx['Amount']}")

def page_search(accounts_ws, transactions_ws):
    st.header("Search Account")
    user_id = st.text_input("Enter ID Number to Search", "")
    if st.button("Search"):
        row_num = find_account_by_id(accounts_ws, user_id)
        if row_num is None:
            st.error("ID not found.")
            return
        
        # Get account data
        account_data = get_account_data(accounts_ws, row_num)
        st.subheader("Account Information")
        st.write(f"**Name:** {account_data['Name']}")
        st.write(f"**Company:** {account_data['Company']}")
        st.write(f"**Creator Agent:** {account_data['CreatorAgent']}")
        st.write(f"**Registration Timestamp:** {account_data['Timestamp']}")
        st.write(f"**Can Have Negative Balance:** {account_data['CanHaveNegativeBalance']}")
        st.write(f"**Current Balance:** {account_data['CurrentBalance']}")

        # Get transactions
        user_transactions = get_transactions_for_id(transactions_ws, user_id)
        st.subheader("Transaction History")

        if not user_transactions:
            st.write("No transactions found for this ID.")
        else:
            # Convert list of dicts to a DataFrame
            df_transactions = pd.DataFrame(user_transactions)
            
            # For nicer column names, rename if you’d like
            df_transactions.rename(columns={
                'Timestamp': 'Date & Time',
                'ID': 'User ID',
                'TransactionType': 'Type',
                'Amount': 'Amount'
            }, inplace=True)

            # Option 1: Use st.table (static table)
            st.table(df_transactions)

            # Option 2 (alternative): Use st.dataframe (interactive table)
            # st.dataframe(df_transactions)


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

    # page selection
    page = st.sidebar.selectbox("Choose a page", 
                                ["Create Account", "Transaction Recorder", "Search Account"])
    
    if page == "Create Account":
        page_create_account(accounts_ws)
    elif page == "Transaction Recorder":
        page_transaction(accounts_ws, transactions_ws)
    elif page == "Search Account":
        page_search(accounts_ws, transactions_ws)


if __name__ == "__main__":
    main()

