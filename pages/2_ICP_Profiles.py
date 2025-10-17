import streamlit as st
from sqlalchemy import text
import pandas as pd

conn = st.connection('data_db', type='sql', connect_args={
    "auth_token": st.secrets.get('TURSO_DB_KEY'),
},)
st.set_page_config(page_title="ICP Profiles", page_icon="🎯")

# Authentication check
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.warning("🔒 Please log in from the main page to access this application.")
    st.stop()

st.markdown("# ICP Profiles")
st.markdown("Build and manage your Ideal Customer Profile personas")

# Show current ICP count
with conn.session as s:
    result = s.execute(text('SELECT COUNT(*) FROM icp_personas;'))
    icp_count = result.scalar()

st.info(f"🎯 Total ICPs: {icp_count}")

# Create/Edit ICP Form
st.markdown("---")
st.markdown("## Create New ICP Profile")

# Check if we're in edit mode
if 'edit_icp' in st.session_state:
    st.markdown("### Editing ICP Profile")
    edit_data = st.session_state.edit_icp
    name = st.text_input("ICP Name/Persona Name", value=edit_data['name'], disabled=True, key='edit_name')
    role = st.text_input("Target Role/Title", value=edit_data['role'], key='edit_role',
                         help="Who is the target person? (e.g., 'Marketing Director', 'VP of Sales')")
    goals = st.text_area("Business Goals", value=edit_data['goals'], key='edit_goals',
                         help="What are their main business objectives?", height=100)
    challenges = st.text_area("Challenges", value=edit_data['challenges'], key='edit_challenges',
                              help="What challenges prevent them from achieving their goals?", height=100)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save Changes", type="primary"):
            with conn.session as s:
                s.execute(text('''
                    UPDATE icp_personas
                    SET role = :role, goals = :goals, challenges = :challenges
                    WHERE name = :name
                '''), {
                    'name': name,
                    'role': role,
                    'goals': goals,
                    'challenges': challenges
                })
                s.commit()
            st.success(f"✓ Successfully updated ICP: {name}")
            del st.session_state.edit_icp
            st.rerun()

    with col2:
        if st.button("Cancel", type="secondary"):
            del st.session_state.edit_icp
            st.rerun()
else:
    # Create new ICP
    name = st.text_input("ICP Name/Persona Name", key='new_name',
                         help="Give this persona a memorable name (e.g., 'Enterprise Emma', 'Startup Steve')")
    role = st.text_input("Target Role/Title", key='new_role',
                         help="Who is the target person? (e.g., 'Marketing Director', 'VP of Sales')")
    goals = st.text_area("Business Goals", key='new_goals',
                         help="What are their main business objectives?", height=100)
    challenges = st.text_area("Challenges", key='new_challenges',
                              help="What challenges prevent them from achieving their goals?", height=100)

    if st.button("Create ICP Profile", type="primary"):
        if not name or not role or not goals or not challenges:
            st.error("All fields are required!")
        else:
            try:
                with conn.session as s:
                    s.execute(text('''
                        INSERT INTO icp_personas (name, role, goals, challenges)
                        VALUES (:name, :role, :goals, :challenges)
                    '''), {
                        'name': name,
                        'role': role,
                        'goals': goals,
                        'challenges': challenges
                    })
                    s.commit()
                st.success(f"✓ Successfully created ICP: {name}")
                st.rerun()
            except Exception as e:
                st.error(f"Error creating ICP: {str(e)}")
                if "UNIQUE constraint failed" in str(e):
                    st.error("An ICP with this name already exists. Please choose a different name.")

# Display existing ICPs
st.markdown("---")
st.markdown("## Existing ICP Profiles")

with conn.session as s:
    result = s.execute(text('SELECT name, role, goals, challenges FROM icp_personas ORDER BY name;'))
    icps = result.fetchall()

if icps:
    # Display as cards for better readability
    for icp in icps:
        with st.expander(f"🎯 {icp[0]} - {icp[1]}"):
            st.markdown(f"**Name:** {icp[0]}")
            st.markdown(f"**Role:** {icp[1]}")
            st.markdown(f"**Goals:**")
            st.write(icp[2])
            st.markdown(f"**Challenges:**")
            st.write(icp[3])

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Edit", key=f"edit_{icp[0]}"):
                    st.session_state.edit_icp = {
                        'name': icp[0],
                        'role': icp[1],
                        'goals': icp[2],
                        'challenges': icp[3]
                    }
                    st.rerun()

            with col2:
                if st.button(f"Delete", key=f"delete_{icp[0]}", type="secondary"):
                    confirm_key = f'confirm_delete_{icp[0]}'
                    if confirm_key not in st.session_state:
                        st.session_state[confirm_key] = True
                        st.warning("⚠️ Click Delete again to confirm")
                        st.rerun()
                    else:
                        with conn.session as s:
                            s.execute(text('DELETE FROM icp_personas WHERE name = :name;'), {'name': icp[0]})
                            s.commit()
                        st.success(f"✓ Deleted ICP: {icp[0]}")
                        del st.session_state[confirm_key]
                        st.rerun()

    # Also show table view
    st.markdown("### Table View")
    df = pd.DataFrame(icps, columns=['Name', 'Role', 'Goals', 'Challenges'])
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No ICP profiles yet. Create your first one above!")

# Clear all ICPs
st.markdown("---")
st.markdown("## Database Management")

if st.button("Clear All ICPs", type="secondary", key='clear_icps'):
    if 'confirm_clear_icps' not in st.session_state:
        st.session_state.confirm_clear_icps = True
        st.warning("⚠️ Click again to confirm deletion of all ICP profiles")
    else:
        with conn.session as s:
            s.execute(text('DELETE FROM icp_personas;'))
            s.commit()
        st.success("✓ All ICP profiles cleared")
        del st.session_state.confirm_clear_icps
        st.rerun()
else:
    if 'confirm_clear_icps' in st.session_state:
        del st.session_state.confirm_clear_icps
