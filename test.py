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
from PIL import Image
# For icon-based sidebar
from streamlit_option_menu import option_menu
import time
from datetime import datetime, date, timedelta


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
    try:
        cell = accounts_ws.find(str(user_id))
        if cell:
            return cell.row
    except gspread.exceptions.CellNotFound:
        pass
    return None

def create_account(accounts_ws, 
                   user_id, 
                   name, 
                   company, 
                   creator_agent, 
                   branch, 
                   can_negative_balance, 
                   phone_number, 
                   registered_by):
    """
    Creates a new account in the 'accounts' worksheet.
    Returns True if successful, or False if the account already exists.

    The 'accounts' sheet columns (9 total) might be:
      A: ID
      B: Name
      C: Company
      D: CreatorAgent
      E: Timestamp
      F: CanHaveNegativeBalance
      G: PhoneNumber
      H: RegisteredBy
      I: Branch
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
        phone_number,        
        registered_by,
        branch
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

def get_account_data(accounts_ws, row_num):
    """
    Returns a dictionary of the account data from a specific row in 'accounts'.
    """
    row_values = accounts_ws.row_values(row_num)
    expected_columns = 9  # Based on your 'accounts' structure

    if len(row_values) < expected_columns:
        row_values += [''] * (expected_columns - len(row_values))
    
    data = {
        "ID": row_values[0],
        "Name": row_values[1],
        "Company": row_values[2],
        "CreatorAgent": row_values[3],
        "Timestamp": row_values[4],
        "CanHaveNegativeBalance": row_values[5],
        "PhoneNumber": row_values[6],
        "RegisteredBy": row_values[7],
        "Branch": row_values[8],
    }
    return data

def update_account_data(accounts_ws, row_num, name, company, creator_agent, can_negative_balance, phone_number, registered_by, branch):
    """
    Updates the editable fields in the 'accounts' worksheet. 
    We do NOT change ID (col A) or Timestamp (col E).
    
    The columns (1-based indexing):
      1 -> A: ID
      2 -> B: Name
      3 -> C: Company
      4 -> D: CreatorAgent
      5 -> E: Timestamp
      6 -> F: CanHaveNegativeBalance
      7 -> G: PhoneNumber
      8 -> H: RegisteredBy
      9 -> I: Branch
    """
    try:
        # Update Name (col 2)
        accounts_ws.update_cell(row_num, 2, name)
        # Update Company (col 3)
        accounts_ws.update_cell(row_num, 3, company)
        # Update CreatorAgent (col 4)
        accounts_ws.update_cell(row_num, 4, creator_agent)
        # Skip col 5 (Timestamp)
        # Update CanHaveNegativeBalance (col 6)
        accounts_ws.update_cell(row_num, 6, str(can_negative_balance))
        # Update PhoneNumber (col 7)
        accounts_ws.update_cell(row_num, 7, phone_number)
        # Update RegisteredBy (col 8)
        accounts_ws.update_cell(row_num, 8, registered_by)
        # Update Branch (col 9)
        accounts_ws.update_cell(row_num, 9, branch)
    except Exception as e:
        st.error(f"Error while updating Google Sheets: {e}")

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

def verify_user(users_ws, username, password):
    """
    Verifies the user's credentials against the 'users' worksheet.
    Returns True if valid, False otherwise.
    """
    try:
        cell = users_ws.find(username)
        if cell:
            stored_password = users_ws.cell(cell.row, cell.col + 1).value
            return stored_password == password
    except gspread.exceptions.CellNotFound:
        pass
    return False

# ----------------------------------
# 1.a) Additional user info
# ----------------------------------

def get_user_info(users_ws, username):
    """
    Fetch user data from 'users' sheet, specifically the 'negative_access' and 'edit_access' columns.
    
    Suppose 'users' sheet columns are:
       A: username
       B: password
       C: negative_access
       D: edit_access
    """
    try:
        cell = users_ws.find(username)
        row = cell.row
        
        negative_access = users_ws.cell(row, cell.col + 2).value
        edit_access = users_ws.cell(row, cell.col + 3).value
        
        # default them to "false" if not present
        if not negative_access:
            negative_access = "false"
        if not edit_access:
            edit_access = "false"
        
        return {
            "negative_access": negative_access.strip().lower(),
            "edit_access": edit_access.strip().lower()
        }
    except gspread.exceptions.CellNotFound:
        return {"negative_access": "false", "edit_access": "false"}

# ----------------------------------
# 1.b) User Balances Helper
# ----------------------------------

# def get_user_balance(user_balances_ws, user_id):
#     """
#     Reads the user's current balance from the 'user_balances' worksheet.
#     Expects two columns: A: id, B: balance
#     Returns the balance as a float or 0.0 if not found.
#     """
#     all_rows = user_balances_ws.get_all_values()  # each row is [id, balance], including header
#     for row in all_rows[1:]:  # skip header if your first row is headers
#         if len(row) >= 2:
#             if str(row[0]) == str(user_id):
#                 try:
#                     return float(row[1])
#                 except ValueError:
#                     return 0.0
#     return 0.0

def get_user_balance(user_balances_ws, user_id):
    """
    Reads the user's current balance from the 'user_balances' worksheet.
    This version uses get_all_records() and expects columns named 'id' and 'balance' (case-insensitive).
    Returns the balance as a float or 0.0 if not found or not parseable.
    """
    # 1) get_all_records() returns a list of dicts, 
    #    automatically using the first row as keys: 
    #    e.g. [{"id": "123", "balance": "-5111"}, {...}, ...]
    records = user_balances_ws.get_all_records()

    for rec in records:
        # Make the key names case-insensitive by lowercasing:
        # But if your sheet columns are literally named "id" and "balance" (all lowercase),
        # then you can just do rec["id"] and rec["balance"] directly.
        # If there are capitalization differences, do something like:
        #    user_id_col = rec.get("ID") or rec.get("id")
        #    balance_col = rec.get("Balance") or rec.get("balance")
        
        # For simplicity, let's assume exact "id" and "balance" in the sheet:
        if str(rec["id"]) == str(user_id):
            try:
                return float(rec["balance"])
            except ValueError:
                return 0.0

    # Not found => 0.0
    return 0.0

# ----------------------------------
# 2) Streamlit Pages
# ----------------------------------

def fetch_all_ids(accounts_ws):
    """
    Fetches all existing ID numbers from the 'accounts' worksheet.
    Returns a list of ID strings.
    """
    try:
        # Assuming IDs are in the first column (A)
        id_column = accounts_ws.col_values(1)
        # Exclude a header if present
        return [id.strip() for id in id_column if id.strip() and id != "ID"]
    except Exception as e:
        st.error(f"Error fetching ID numbers: {e}")
        return []

def page_create_account(accounts_ws):
    st.header("Create New Account")
    
    # Define the list of companies for the dropdown
    companies_list = [
        "نقل",
        "توزيع",
        "إنتاج",
        "أنابيب البترول",
        "بتروجيت",
        "بنك مصر",
        "النصر",
        "تبديل",
        "MEDRIGHT",
        "GLOBEMED",
        "AXA",
        "Alico"
    ]
    
    # Define the list of branches for the dropdown
    branches_list = [
        "Nasser",
        "Suez",
        "Arbeen",
        "Farz"
    ]
    
    with st.form("create_account_form"):
        user_id = st.text_input("ID Number", "").strip()
        name = st.text_input("Name", "").strip()
        company = st.selectbox("Company", companies_list)
        creator_agent = st.text_input("Creator Agent", "").strip()
        phone_number = st.text_input("Phone Number", "").strip()
        branch = st.selectbox("Branch", branches_list)  
        
        # Only allow negative balance checkbox if user has negative_access == "true"
        if st.session_state.get("negative_access", "false") == "true":
            can_negative_balance = st.checkbox("Can have negative balance?", value=False)
        else:
            st.info("You **do not** have permission to enable negative balance. This option is disabled.")
            can_negative_balance = False
        
        submitted = st.form_submit_button("Create Account")

        if submitted:
            # Validation
            valid = True

            # Check for empty fields
            if not user_id or not name or not creator_agent or not phone_number or not branch:
                st.error("All fields are required.")
                valid = False

            # Validate ID Number: exactly 14 digits, numeric
            if not user_id.isdigit() or len(user_id) != 14:
                st.error("ID Number must be exactly 14 digits and contain only numbers.")
                valid = False

            # Validate Phone Number: exactly 11 digits, numeric
            if not phone_number.isdigit() or len(phone_number) != 11:
                st.error("Phone Number must be exactly 11 digits and contain only numbers.")
                valid = False

            if valid:
                # Assign 'RegisteredBy' as the currently logged-in user
                registered_by = st.session_state.username

                success = create_account(accounts_ws,
                                         user_id,
                                         name,
                                         company,
                                         creator_agent,
                                         branch,  
                                         can_negative_balance,
                                         phone_number,
                                         registered_by)
                if success:
                    st.success(f"Account for ID {user_id} created successfully!")
                else:
                    st.error(f"Account with ID {user_id} already exists.")

def page_edit_account(accounts_ws):
    """
    Allows editing existing account data but NOT Timestamp, ID, RegisteredBy, or CreatorAgent.
    Only users who have edit_access == 'true' can actually make changes.
    """
    st.header("Edit Registered Account")
    
    # 1) Check if user can edit
    if st.session_state.get("edit_access", "false") != "true":
        st.warning("You do not have permission to edit accounts.")
        return

    # 2) Hardcoded dropdown lists
    companies_list = [
        "نقل", "توزيع", "إنتاج", "أنابيب البترول", 
        "بتروجيت", "بنك مصر", "النصر", "تبديل", 
        "MEDRIGHT", "GLOBEMED", "AXA", "Alico"
    ]
    branches_list = [
        "Nasser", 
        "Suez", 
        "Arbeen", 
        "Farz"
    ]

    # 3) Input for ID
    user_id = st.text_input("Enter the ID of the account you want to edit", "").strip()

    # 4) "Search" button
    if st.button("Search"):
        # CLEAR OUT any old edit_data from a previous user
        if "edit_data" in st.session_state:
            del st.session_state["edit_data"]

        if not user_id:
            st.error("Please enter an ID.")
        else:
            # Find row
            row_num = find_account_by_id(accounts_ws, user_id)
            if row_num is None:
                st.error(f"No account found with ID {user_id}.")
            else:
                # Store in session_state for editing
                st.session_state.edit_data = {
                    "row_num": row_num,
                    "account_data": get_account_data(accounts_ws, row_num)
                }
                st.success(f"Account for ID {user_id} fetched successfully. Edit below.")

    # 5) If we have data in session_state, show the form
    if "edit_data" in st.session_state and "account_data" in st.session_state.edit_data:
        row_num = st.session_state.edit_data["row_num"]
        account_data = st.session_state.edit_data["account_data"]

        with st.form("edit_account_form"):
            # -- READ-ONLY Fields
            st.write(f"**ID**: {account_data['ID']}")
            st.write(f"**Timestamp**: {account_data['Timestamp']}")
            st.write(f"**Creator Agent**: {account_data['CreatorAgent']}")
            st.write(f"**Registered By**: {account_data['RegisteredBy']}")

            # -- EDITABLE Fields
            new_name = st.text_input("Name", value=account_data["Name"])

            # Company Dropdown
            company_in_sheet = account_data["Company"].strip()
            temp_companies = companies_list[:]  # copy so we don't modify original
            if company_in_sheet not in temp_companies:
                temp_companies.insert(0, company_in_sheet)
            company_index = temp_companies.index(company_in_sheet) if company_in_sheet in temp_companies else 0
            new_company = st.selectbox("Company", temp_companies, index=company_index)

            # Negative Balance?
            if st.session_state.get("negative_access", "false") == "true":
                can_negative_default = (account_data["CanHaveNegativeBalance"].lower() == "true")
                new_can_negative = st.checkbox("Can have negative balance?", value=can_negative_default)
            else:
                st.write(f"Can Have Negative Balance: {account_data['CanHaveNegativeBalance']}")
                new_can_negative = (account_data["CanHaveNegativeBalance"].lower() == "true")

            # Phone
            new_phone_number = st.text_input("Phone Number", value=account_data["PhoneNumber"])

            # Branch Dropdown
            branch_in_sheet = account_data["Branch"].strip()
            temp_branches = branches_list[:] 
            if branch_in_sheet not in temp_branches:
                temp_branches.insert(0, branch_in_sheet)
            branch_index = temp_branches.index(branch_in_sheet) if branch_in_sheet in temp_branches else 0
            new_branch = st.selectbox("Branch", temp_branches, index=branch_index)

            # 6) "Save Changes" button
            submitted_edit = st.form_submit_button("Save Changes")
            if submitted_edit:
                # Basic validation
                if not new_name.strip():
                    st.error("Name cannot be empty.")
                    return
                if not new_phone_number.isdigit() or len(new_phone_number) != 11:
                    st.error("Phone Number must be exactly 11 digits and contain only numbers.")
                    return

                # 7) Perform the update
                try:
                    update_account_data(
                        accounts_ws,
                        row_num,
                        new_name,
                        new_company,
                        account_data["CreatorAgent"],  # preserve original
                        new_can_negative,
                        new_phone_number,
                        account_data["RegisteredBy"],   # preserve original
                        new_branch
                    )
                    st.success("Account updated successfully!")
                except Exception as e:
                    st.error(f"Error while updating account: {e}")

# def page_transaction(accounts_ws, transactions_ws, user_balances_ws):
#     st.header("Transaction Recorder")
#     with st.form("transaction_form"):
#         user_id = st.text_input("ID Number", "")
#         transaction_type = st.selectbox("Transaction Type", ["ADD", "DEDUCT"])
#         amount = st.number_input("Amount", min_value=0.0, max_value=5000.0, step=1.0)
        
#         branch = st.selectbox("Branch", ["Nasser", "Suez", "Arbeen", "Farz"])
#         agent_name = st.text_input("Agent Name", "")

#         submitted = st.form_submit_button("Record Transaction")

#         if submitted:
#             if agent_name.strip() == "":
#                 st.error("Please provide the agent name.")
#                 return
            
#             # 1) Find account row
#             row_num = find_account_by_id(accounts_ws, user_id)
#             if row_num is None:
#                 st.error("ID not found in 'accounts'. Please create an account first.")
#                 return

#             # 2) Get account data
#             account_data = get_account_data(accounts_ws, row_num)

#             # 3) Read current balance from 'user_balances'
#             current_balance = get_user_balance(user_balances_ws, user_id)

#             # 4) Check negative balance allowance
#             can_neg_raw = account_data["CanHaveNegativeBalance"].strip().lower()
#             can_negative = (can_neg_raw == "true")

#             # 5) Calculate new balance
#             if transaction_type == "ADD":
#                 new_balance = current_balance + amount
#                 record_transaction(transactions_ws, user_id, transaction_type, amount, branch, agent_name)
#                 st.success(f"Transaction recorded: +{amount} to ID {user_id}.")
            
#             else:  # "DEDUCT"
#                 new_balance = current_balance - amount
#                 if new_balance < 0 and not can_negative:
#                     st.error("This account does not allow a negative balance. Transaction rejected.")
#                     return
#                 record_transaction(transactions_ws, user_id, transaction_type, amount, branch, agent_name)
#                 st.success(f"Transaction recorded: -{amount} from ID {user_id}.")


def page_transaction(accounts_ws, transactions_ws, user_balances_ws):
    st.header("Transaction Recorder")

    # 1) Retrieve whatever is in session_state, or default to ""
    typed_id = st.session_state.get("current_user_id", "")

    # 2) Show the text_input. No key is given.
    user_id = st.text_input("ID Number", value=typed_id)

    # 3) Update session_state with what the user typed
    st.session_state["current_user_id"] = user_id

    # 4) Show current balance if we have an ID
    if user_id:
        current_balance = get_user_balance(user_balances_ws, user_id)
        if current_balance < 0:
            st.markdown(
                f"<p style='color:red; font-weight:bold;'>"
                f"Current Balance: {current_balance:.2f} EGP</p>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"<p style='color:green; font-weight:bold;'>"
                f"Current Balance: {current_balance:.2f} EGP</p>",
                unsafe_allow_html=True
            )
    
    # st.session_state["current_user_id"] = ""
    # st.session_state["transaction_type"] = " "
    # st.session_state["amount"] = 0.0
    # st.session_state["branch"] = " "
    # st.session_state["agent_name"] = " "

    # 5) The transaction form
    with st.form("transaction_form"):
        transaction_type = st.selectbox("Transaction Type", ["ADD", "DEDUCT"])
        amount = st.number_input("Amount", min_value=0.0, max_value=5000.0, step=1.0)
        branch = st.selectbox("Branch", ["Nasser", "Suez", "Arbeen", "Farz"])
        agent_name = st.text_input("Agent Name", "")

        submitted = st.form_submit_button("Record Transaction")
        if submitted:
            # Validation
            if not user_id:
                st.error("Please enter an ID first.")
                return

            if not agent_name.strip():
                st.error("Please provide the agent name.")
                return

            # Find account
            row_num = find_account_by_id(accounts_ws, user_id)
            if row_num is None:
                st.error("ID not found in 'accounts'. Please create an account first.")
                return

            # Current balance
            account_data = get_account_data(accounts_ws, row_num)
            current_balance = get_user_balance(user_balances_ws, user_id)

            # Negative balance check
            can_neg_raw = account_data["CanHaveNegativeBalance"].strip().lower()
            can_negative = (can_neg_raw == "true")

            # Perform transaction
            if transaction_type == "ADD":
                new_balance = current_balance + amount
                record_transaction(transactions_ws, user_id, transaction_type, amount, branch, agent_name)
                st.success(f"Transaction recorded: +{amount} to ID {user_id}.")
            else:  # "DEDUCT"
                new_balance = current_balance - amount
                if new_balance < 0 and not can_negative:
                    st.error("This account does not allow a negative balance. Transaction rejected.")
                    return
                record_transaction(transactions_ws, user_id, transaction_type, amount, branch, agent_name)
                st.success(f"Transaction recorded: -{amount} from ID {user_id}.")

            # Show updated balance
            if new_balance < 0:
                st.markdown(
                    f"<p style='color:red; font-weight:bold;'>"
                    f"Updated Balance: {new_balance:.2f} EGP</p>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"<p style='color:green; font-weight:bold;'>"
                    f"Updated Balance: {new_balance:.2f} EGP</p>",
                    unsafe_allow_html=True
                )

            # Clear the user ID from session state so it doesn’t show old balance next time
            st.session_state["current_user_id"] = ""
            
            st.info("Refreshing in 5 seconds...")
            time.sleep(5)

            st.rerun()

def page_search(accounts_ws, transactions_ws, user_balances_ws):
    st.header("Search Account")
    user_id = st.text_input("Enter ID Number to Search", "").strip()
    
    if st.button("Search"):
        if not user_id:
            st.error("Please enter an ID Number to search.")
            return

        row_num = find_account_by_id(accounts_ws, user_id)
        if row_num is None:
            st.error("ID not found in 'accounts'.")
            return

        # --- 1) Get account data
        account_data = get_account_data(accounts_ws, row_num)

        # --- 2) Get current balance from 'user_balances'
        current_balance_val = get_user_balance(user_balances_ws, user_id)
        balance_str = f"{current_balance_val:,.2f} EGP"

        # --- 3) Prepare and display basic account info
        df_info = pd.DataFrame({
            'Parameter': [
                "Name", 
                "Company",
                "Branch",
                "Creator Agent",
                "Registration Timestamp", 
                "Can Have Negative Balance", 
                "Current Balance",
                "Phone Number",
                "Registered By"
            ],
            'Value': [
                account_data['Name'],
                account_data['Company'],
                account_data['Branch'],
                account_data['CreatorAgent'],
                account_data['Timestamp'],
                account_data['CanHaveNegativeBalance'],
                balance_str,
                account_data['PhoneNumber'],
                account_data['RegisteredBy']
            ]
        })

        # Highlight function for negative vs positive balance
        def highlight_balance(value):
            if "EGP" in value:
                numeric_part = value.replace(' EGP', '').replace(',', '')
                try:
                    numeric_val = float(numeric_part)
                    if numeric_val < 0:
                        return 'color: red; font-weight: bold;'
                    else:
                        return 'color: green; font-weight: bold;'
                except ValueError:
                    return ''
            return ''

        df_info_styled = df_info.style.applymap(highlight_balance, subset=[df_info.columns[1]])
        st.write(df_info_styled.to_html(), unsafe_allow_html=True)

        # --- 4) Fetch and display transaction history
        user_transactions = get_transactions_for_id(transactions_ws, user_id)
        st.subheader("Transaction History")

        if not user_transactions:
            st.write("No transactions found for this ID.")
        else:
            df_transactions = pd.DataFrame(user_transactions)
            # Rename columns for nicer display
            df_transactions.rename(columns={
                'Timestamp': 'Date & Time',
                'ID': 'User ID',
                'TransactionType': 'Type',
                'Amount': 'Amount',
                'Branch': 'Branch',
                'AgentName': 'Agent Name'
            }, inplace=True)
            
            # Convert to datetime for sorting
            df_transactions['Date & Time'] = pd.to_datetime(df_transactions['Date & Time'], errors='coerce')
            # Sort descending (latest first)
            df_transactions = df_transactions.sort_values(by='Date & Time', ascending=False)
            # Format the datetime
            df_transactions['Date & Time'] = df_transactions['Date & Time'].dt.strftime('%Y-%m-%d %H:%M:%S')

            st.table(df_transactions)

def page_audit_dashboard(accounts_ws, transactions_ws, user_balances_ws):
    """
    Provides filters for Transaction and User data, then displays
    the filtered results in separate sections.
    """
    st.title("Audit Dashboard")

    # --- Fetch raw data from Google Sheets
    df_accounts = pd.DataFrame(accounts_ws.get_all_records())
    df_transactions = pd.DataFrame(transactions_ws.get_all_records())
    df_balances = pd.DataFrame(user_balances_ws.get_all_records())

    # Make sure columns exist
    # For accounts, we assume columns: ['ID','Name','Company','CreatorAgent','Timestamp','CanHaveNegativeBalance','PhoneNumber','RegisteredBy','Branch']
    # For transactions: ['Timestamp','ID','TransactionType','Amount','Branch','AgentName']
    # For balances:     ['id','balance'] (per your code)

    # Convert date columns to datetime for easier filtering
    if not df_accounts.empty and 'Timestamp' in df_accounts.columns:
        df_accounts['Timestamp'] = pd.to_datetime(df_accounts['Timestamp'], errors='coerce')
    if not df_transactions.empty and 'Timestamp' in df_transactions.columns:
        df_transactions['Timestamp'] = pd.to_datetime(df_transactions['Timestamp'], errors='coerce')

    # ----------------------------
    # 1) TRANSACTION FILTERS
    # ----------------------------
    st.subheader("Filter: Transactions")

    # A) Start Date & End Date for Transactions
    #    Default: last 30 days
    today = datetime.date.today()
    default_start = today - datetime.timedelta(days=30)

    col1, col2 = st.columns(2)
    with col1:
        start_date_t = st.date_input("Transaction Start Date", value=default_start)
    with col2:
        end_date_t = st.date_input("Transaction End Date", value=today)

    # B) Branch filter (with "All" option)
    branch_options = sorted(df_transactions['Branch'].unique()) if 'Branch' in df_transactions.columns else []
    branch_options = ["All"] + branch_options
    selected_branch_t = st.selectbox("Transaction Branch", branch_options, index=0)

    # C) Company filter (with "All" option)
    #    Note: Transactions themselves don't store company, but we can join on the "ID"
    #    to get the user’s company from df_accounts.
    company_options = sorted(df_accounts['Company'].unique()) if 'Company' in df_accounts.columns else []
    company_options = ["All"] + company_options
    selected_company_t = st.selectbox("Transaction Company", company_options, index=0)

    # ----------------------------
    # 2) APPLY TRANSACTION FILTERS
    # ----------------------------
    df_transactions_filtered = df_transactions.copy()

    # Filter by date
    if not df_transactions_filtered.empty and 'Timestamp' in df_transactions_filtered.columns:
        df_transactions_filtered = df_transactions_filtered[
            (df_transactions_filtered['Timestamp'] >= pd.to_datetime(start_date_t)) &
            (df_transactions_filtered['Timestamp'] <= pd.to_datetime(end_date_t) + pd.Timedelta(days=1))
        ]

    # Filter by branch
    if selected_branch_t != "All" and 'Branch' in df_transactions_filtered.columns:
        df_transactions_filtered = df_transactions_filtered[df_transactions_filtered['Branch'] == selected_branch_t]

    # Filter by company => join df_transactions with df_accounts on ID to get Company
    if selected_company_t != "All":
        if not df_accounts.empty and 'ID' in df_accounts.columns and 'Company' in df_accounts.columns:
            # We can do a merge to bring "Company" into the transactions
            merged_t = df_transactions_filtered.merge(df_accounts[['ID','Company']], 
                                                      left_on='ID', 
                                                      right_on='ID', 
                                                      how='left')
            # Now filter by the selected company
            merged_t = merged_t[merged_t['Company'] == selected_company_t]
            df_transactions_filtered = merged_t
        else:
            # If data is missing, then no transactions match
            df_transactions_filtered = df_transactions_filtered.iloc[0:0]

    # Show the filtered transactions
    st.write("### Filtered Transactions")
    if df_transactions_filtered.empty:
        st.info("No transaction records match the selected filters.")
    else:
        # Sort descending by date
        df_transactions_filtered = df_transactions_filtered.sort_values(by='Timestamp', ascending=False)
        df_transactions_filtered.reset_index(drop=True, inplace=True)
        st.dataframe(df_transactions_filtered)

    st.markdown("---")

    # ----------------------------
    # 3) USER/ACCOUNTS FILTERS
    # ----------------------------
    st.subheader("Filter: Users / Accounts")

    # A) Registration Start/End Date
    #    Also default to last 30 days
    col3, col4 = st.columns(2)
    with col3:
        start_date_u = st.date_input("Registration Start Date", value=default_start)
    with col4:
        end_date_u = st.date_input("Registration End Date", value=today)

    # B) User Company (with "All" option)
    company_options_u = sorted(df_accounts['Company'].unique()) if 'Company' in df_accounts.columns else []
    company_options_u = ["All"] + company_options_u
    selected_company_u = st.selectbox("User Company", company_options_u, index=0)

    # C) User Branch (with "All" option)
    branch_options_u = sorted(df_accounts['Branch'].unique()) if 'Branch' in df_accounts.columns else []
    branch_options_u = ["All"] + branch_options_u
    selected_branch_u = st.selectbox("User Branch", branch_options_u, index=0)

    # D) User Balance Tag
    #    "no_balance" (== 0), "positive_balance" (> 0), "negative_balance" (< 0), or "All"
    balance_tags = ["All", "no_balance", "positive_balance", "negative_balance"]
    selected_balance_tag = st.selectbox("User Balance Tag", balance_tags, index=0)

    # ----------------------------
    # 4) APPLY USER/ACCOUNTS FILTERS
    # ----------------------------
    df_accounts_filtered = df_accounts.copy()

    # Filter by registration timestamp
    if not df_accounts_filtered.empty and 'Timestamp' in df_accounts_filtered.columns:
        df_accounts_filtered = df_accounts_filtered[
            (df_accounts_filtered['Timestamp'] >= pd.to_datetime(start_date_u)) &
            (df_accounts_filtered['Timestamp'] <= pd.to_datetime(end_date_u) + pd.Timedelta(days=1))
        ]

    # Filter by company
    if selected_company_u != "All":
        df_accounts_filtered = df_accounts_filtered[df_accounts_filtered['Company'] == selected_company_u]

    # Filter by branch
    if selected_branch_u != "All":
        df_accounts_filtered = df_accounts_filtered[df_accounts_filtered['Branch'] == selected_branch_u]

    # Convert df_balances for easy lookups:  key => user_id, value => balance
    balances_dict = {}
    if not df_balances.empty:
        for idx, row in df_balances.iterrows():
            # row['id'], row['balance']
            balances_dict[str(row.get('id', ''))] = row.get('balance', 0.0)

    # Compute each user’s balance from balances_dict
    df_accounts_filtered['CurrentBalance'] = df_accounts_filtered['ID'].astype(str).apply(
        lambda user_id: float(balances_dict.get(user_id, 0.0))
    )

    # Filter by balance tag
    if selected_balance_tag != "All":
        if selected_balance_tag == "no_balance":
            df_accounts_filtered = df_accounts_filtered[df_accounts_filtered['CurrentBalance'] == 0]
        elif selected_balance_tag == "positive_balance":
            df_accounts_filtered = df_accounts_filtered[df_accounts_filtered['CurrentBalance'] > 0]
        elif selected_balance_tag == "negative_balance":
            df_accounts_filtered = df_accounts_filtered[df_accounts_filtered['CurrentBalance'] < 0]

    # Show the filtered accounts
    st.write("### Filtered Users / Accounts")
    if df_accounts_filtered.empty:
        st.info("No user accounts match the selected filters.")
    else:
        # Sort by registration timestamp descending
        df_accounts_filtered = df_accounts_filtered.sort_values(by='Timestamp', ascending=False)
        df_accounts_filtered.reset_index(drop=True, inplace=True)
        st.dataframe(df_accounts_filtered)

# ----------------------------------
# 2.a) Modified Login to also get edit_access
# ----------------------------------

def page_login(users_ws):
    st.title("Login")
    
    # Display logout success message if applicable
    if 'logout' in st.session_state and st.session_state.logout:
        st.success("You have been logged out.")
        st.session_state.logout = False
    
    with st.form("login_form"):
        username = st.text_input("Username").strip()
        password = st.text_input("Password", type="password").strip()
        submitted = st.form_submit_button("Login")

        if submitted:
            # Basic validation
            if not username or not password:
                st.error("Please enter both username and password.")
                return

            # Verify credentials
            if verify_user(users_ws, username, password):
                st.success("Login successful!")
                st.session_state.logged_in = True
                st.session_state.username = username

                # Now fetch negative_access and edit_access
                user_info = get_user_info(users_ws, username)
                st.session_state.negative_access = user_info['negative_access']
                st.session_state.edit_access = user_info['edit_access']

                st.rerun()
            else:
                st.error("Invalid username or password.")

def page_logout():
    """
    Handles user logout by resetting session state.
    """
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.logout = True
    # Reset or remove negative_access and edit_access
    st.session_state.negative_access = "false"
    st.session_state.edit_access = "false"
    st.rerun()

# ----------------------------------
# 3) Main Streamlit App
# ----------------------------------

def main():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'username' not in st.session_state:
        st.session_state.username = ""
    if 'logout' not in st.session_state:
        st.session_state.logout = False
    if 'negative_access' not in st.session_state:
        st.session_state.negative_access = "false"
    if 'edit_access' not in st.session_state:
        st.session_state.edit_access = "false"

    try:
        client = init_connection()
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return

    SHEET_NAME = "database"
    try:
        accounts_ws = get_worksheet(client, SHEET_NAME, "accounts")
        transactions_ws = get_worksheet(client, SHEET_NAME, "transactions")
        user_balances_ws = get_worksheet(client, SHEET_NAME, "user_balances")
    except gspread.exceptions.WorksheetNotFound as e:
        st.error(f"Worksheet not found: {e}")
        return
    
    # Load users for login
    try:
        users_ws = get_worksheet(client, SHEET_NAME, "users")
    except gspread.exceptions.WorksheetNotFound:
        st.error("The 'users' worksheet was not found in the Google Sheets database.")
        return

    if not st.session_state.logged_in:
        page_login(users_ws)
        return

    # Logo
    try:
        image = Image.open("logo.png")
        st.image(image, use_container_width=True)
    except FileNotFoundError:
        st.warning("Logo image not found. Please ensure 'logo.png' is in the correct directory.")

    st.title("Elreedy Pharmacies System")
    st.write(f"Welcome, **{st.session_state.username}**!")

    # --------------------------------------------
    # Sidebar with Navigation & Logout
    # --------------------------------------------
    with st.sidebar:
        selected_page = option_menu(
            menu_title=None,  
            options=[
                "Create Account", 
                "Transaction Recorder", 
                "Search Account", 
                "Edit Account",
                "Audit Dashboard"
            ],
            icons=[
                "person-plus", 
                "cash-coin", 
                "search", 
                "pencil-square",
                "bar-chart-line-fill"
            ],  
            default_index=0,
            orientation="vertical",
        )
        
        st.markdown("---")
        if st.button("Logout", key="logout_button"):
            page_logout()

    # Route pages
    if selected_page == "Create Account":
        page_create_account(accounts_ws)
    elif selected_page == "Transaction Recorder":
        page_transaction(accounts_ws, transactions_ws, user_balances_ws)
    elif selected_page == "Search Account":
        page_search(accounts_ws, transactions_ws, user_balances_ws)
    elif selected_page == "Edit Account":
        page_edit_account(accounts_ws)
    elif selected_page == "Audit Dashboard":
        page_audit_dashboard(accounts_ws, transactions_ws, user_balances_ws)

if __name__ == "__main__":
    main()


