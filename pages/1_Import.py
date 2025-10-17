import streamlit as st
import time
import numpy as np
from sqlalchemy import text
import pandas as pd

conn = st.connection('data_db', type='sql', connect_args={
    "auth_token": st.secrets.get('TURSO_DB_KEY'),
},)
with conn.session as s:
    # ICP Table - Extended with role, goals, challenges
    s.execute(text('CREATE TABLE IF NOT EXISTS icp_personas (name TEXT PRIMARY KEY, role TEXT, goals TEXT, challenges TEXT);'))

    # Peec Domains Table (Domain	Type	Used	Avg. Citations)
    s.execute(text('CREATE TABLE IF NOT EXISTS peec_domains (domain TEXT PRIMARY KEY, type TEXT, percent REAL, citiatons REAL);'))

    # Peec Chat Table (id	model	user	assistant	model)
    s.execute(text('CREATE TABLE IF NOT EXISTS peec_chats (id TEXT PRIMARY KEY, model TEXT, user TEXT, assistant TEXT);'))

    s.commit()

st.set_page_config(page_title="Import", page_icon="🌍")

# Authentication check
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.warning("🔒 Please log in from the main page to access this application.")
    st.stop()

st.markdown("# Import")

# Show current database status
with conn.session as s:
    result = s.execute(text('SELECT COUNT(*) FROM peec_domains;'))
    domain_count = result.scalar()
    result2 = s.execute(text('SELECT COUNT(*) FROM peec_chats;'))
    chat_count = result2.scalar()

col1, col2 = st.columns(2)
with col1:
    st.info(f"📊 Domains: {domain_count}")
with col2:
    st.info(f"💬 Chats: {chat_count}")

st.markdown("## Upload Domains CSV")
st.markdown("Upload a CSV file with columns: **Domain**, **Type**, **Used**, **Avg. Citations**")

# File uploader
uploaded_file = st.file_uploader("Choose a CSV file", type=['csv'])

if uploaded_file is not None:
    # Read CSV
    try:
        df = pd.read_csv(uploaded_file)

        # Validation
        REQUIRED_COLUMNS = ['Domain', 'Type', 'Used', 'Avg. Citations']
        VALID_TYPES = ['UGC', 'Competitor', 'Corporate', 'Other', 'Editorial']

        validation_errors = []

        # Check columns
        missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_columns:
            validation_errors.append(f"Missing required columns: {', '.join(missing_columns)}")

        if not validation_errors and len(df) > 0:
            # Validate values
            if df['Domain'].isna().any() or (df['Domain'] == '').any():
                validation_errors.append("Some domains are empty")

            # Check numeric columns
            try:
                df['Used_numeric'] = pd.to_numeric(df['Used'].astype(str).str.rstrip('%'), errors='coerce')
                if df['Used_numeric'].isna().any():
                    validation_errors.append("'Used' column contains non-numeric values")
            except:
                validation_errors.append("'Used' column cannot be converted to numeric")

            try:
                df['Citations_numeric'] = pd.to_numeric(df['Avg. Citations'], errors='coerce')
                if df['Citations_numeric'].isna().any():
                    validation_errors.append("'Avg. Citations' column contains non-numeric values")
            except:
                validation_errors.append("'Avg. Citations' column cannot be converted to numeric")

            # Type whitelist
            invalid_types = df[~df['Type'].isin(VALID_TYPES)]['Type'].unique()
            if len(invalid_types) > 0:
                validation_errors.append(f"Invalid Type values found: {', '.join(invalid_types)}. Must be one of: {', '.join(VALID_TYPES)}")

        if validation_errors:
            st.error("Validation failed:")
            for error in validation_errors:
                st.error(f"• {error}")
        else:
            st.success("✓ CSV validation passed")

            # Preview
            st.markdown("### Data Preview")
            st.dataframe(df.head(20), use_container_width=True)

            # Summary statistics
            st.markdown("### Summary Statistics")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Domains", len(df))
            with col2:
                st.metric("Unique Types", df['Type'].nunique())
            with col3:
                st.metric("Avg Citations", f"{df['Citations_numeric'].mean():.1f}")

            st.markdown("#### Type Distribution")
            type_counts = df['Type'].value_counts()
            st.bar_chart(type_counts)

            # Import button
            if st.button("Import to Database", type="primary"):
                with st.spinner("Importing data..."):
                    with conn.session as s:
                        for _, row in df.iterrows():
                            s.execute(text('''
                                INSERT OR REPLACE INTO peec_domains (domain, type, percent, citiatons)
                                VALUES (:domain, :type, :percent, :citations)
                            '''), {
                                'domain': row['Domain'],
                                'type': row['Type'],
                                'percent': row['Used_numeric'],
                                'citations': row['Citations_numeric']
                            })
                        s.commit()
                st.success(f"✓ Successfully imported {len(df)} domains!")
                st.rerun()

    except Exception as e:
        st.error(f"Error reading CSV file: {str(e)}")

# Chats CSV Upload Section
st.markdown("---")
st.markdown("## Upload Chats CSV")
st.markdown("Upload a CSV file with columns: **id**, **model**, **user**, **assistant** (other columns will be ignored)")

# File uploader for chats
uploaded_chats_file = st.file_uploader("Choose a chats CSV file", type=['csv'], key='chats_uploader')

if uploaded_chats_file is not None:
    # Read CSV
    try:
        df_chats = pd.read_csv(uploaded_chats_file)

        # Validation
        REQUIRED_CHAT_COLUMNS = ['id', 'model', 'user', 'assistant']

        validation_errors = []

        # Check columns
        missing_columns = [col for col in REQUIRED_CHAT_COLUMNS if col not in df_chats.columns]
        if missing_columns:
            validation_errors.append(f"Missing required columns: {', '.join(missing_columns)}")

        if not validation_errors and len(df_chats) > 0:
            # Validate values
            if df_chats['id'].isna().any() or (df_chats['id'] == '').any():
                validation_errors.append("Some chat IDs are empty")

            if df_chats['model'].isna().any() or (df_chats['model'] == '').any():
                validation_errors.append("Some model values are empty")

            # user and assistant can be empty, so no validation needed

        if validation_errors:
            st.error("Validation failed:")
            for error in validation_errors:
                st.error(f"• {error}")
        else:
            st.success("✓ CSV validation passed")

            # Show only relevant columns in preview
            df_chats_display = df_chats[REQUIRED_CHAT_COLUMNS].copy()

            # Preview
            st.markdown("### Data Preview")
            st.dataframe(df_chats_display.head(20), use_container_width=True)

            # Summary statistics
            st.markdown("### Summary Statistics")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Chats", len(df_chats))
            with col2:
                st.metric("Unique Models", df_chats['model'].nunique())
            with col3:
                responses_count = df_chats[df_chats['assistant'].notna() & (df_chats['assistant'] != '')].shape[0]
                response_pct = (responses_count / len(df_chats) * 100) if len(df_chats) > 0 else 0
                st.metric("With Responses", f"{response_pct:.1f}%")

            st.markdown("#### Model Distribution")
            model_counts = df_chats['model'].value_counts()
            st.bar_chart(model_counts)

            # Import button
            if st.button("Import Chats to Database", type="primary", key='import_chats'):
                with st.spinner("Importing chats..."):
                    with conn.session as s:
                        for _, row in df_chats.iterrows():
                            s.execute(text('''
                                INSERT OR REPLACE INTO peec_chats (id, model, user, assistant)
                                VALUES (:id, :model, :user, :assistant)
                            '''), {
                                'id': row['id'],
                                'model': row['model'],
                                'user': row['user'] if pd.notna(row['user']) else '',
                                'assistant': row['assistant'] if pd.notna(row['assistant']) else ''
                            })
                        s.commit()
                st.success(f"✓ Successfully imported {len(df_chats)} chats!")
                st.rerun()

    except Exception as e:
        st.error(f"Error reading CSV file: {str(e)}")

# Clear database functionality
st.markdown("---")
st.markdown("## Database Management")

col1, col2 = st.columns(2)

with col1:
    if st.button("Clear All Domains", type="secondary", key='clear_domains'):
        if 'confirm_clear_domains' not in st.session_state:
            st.session_state.confirm_clear_domains = True
            st.warning("⚠️ Click again to confirm deletion of all domains")
        else:
            with conn.session as s:
                s.execute(text('DELETE FROM peec_domains;'))
                s.commit()
            st.success("✓ All domains cleared")
            del st.session_state.confirm_clear_domains
            st.rerun()
    else:
        if 'confirm_clear_domains' in st.session_state:
            del st.session_state.confirm_clear_domains

with col2:
    if st.button("Clear All Chats", type="secondary", key='clear_chats'):
        if 'confirm_clear_chats' not in st.session_state:
            st.session_state.confirm_clear_chats = True
            st.warning("⚠️ Click again to confirm deletion of all chats")
        else:
            with conn.session as s:
                s.execute(text('DELETE FROM peec_chats;'))
                s.commit()
            st.success("✓ All chats cleared")
            del st.session_state.confirm_clear_chats
            st.rerun()
    else:
        if 'confirm_clear_chats' in st.session_state:
            del st.session_state.confirm_clear_chats
