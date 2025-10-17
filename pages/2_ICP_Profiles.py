import streamlit as st
from sqlalchemy import text
import pandas as pd
import json
from openai import OpenAI

# Initialize OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=st.secrets.get("OPENAI_API_KEY") or "",
)

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

# AI-Suggested ICPs Section
st.markdown("---")
st.markdown("## AI-Suggested ICP Profiles")
st.caption("Generate ICP suggestions based on your brand information")

# Initialize session state for suggestions
if 'icp_suggestions' not in st.session_state:
    st.session_state.icp_suggestions = None

def generate_icp_suggestions():
    """Generate ICP suggestions using OpenRouter AI based on brand info"""
    try:
        # Load brand info
        with conn.session as s:
            result = s.execute(text('SELECT name, url, description FROM brand_info WHERE id = 1;'))
            brand = result.fetchone()

        if not brand or not brand[0]:
            st.error("No brand information found. Please configure your brand on the main page first.")
            return None

        brand_name = brand[0]
        brand_url = brand[1]
        brand_description = brand[2] or "No description available"

        # Create the prompt for ICP generation
        system_prompt = """You are an expert marketing strategist who specializes in developing Ideal Customer Profiles (ICPs).
Your task is to analyze brand information and generate 2-3 highly specific ICP personas that would be the best fit for this brand.

For each ICP, provide:
1. A memorable persona name (e.g., "Enterprise Emma", "Startup Steve")
2. Their specific role/title
3. Their key business goals (2-3 concrete objectives)
4. Their main challenges (2-3 specific pain points)

Return your response as a JSON object with this exact structure:
{
  "icps": [
    {
      "name": "Persona name here",
      "role": "Specific job title",
      "goals": "Bullet points of 2-3 business goals they're trying to achieve",
      "challenges": "Bullet points of 2-3 challenges preventing them from achieving those goals"
    }
  ],
  "rationale": "Brief explanation of why these ICPs were selected for this brand"
}"""

        user_prompt = f"""Brand Information:
- Name: {brand_name}
- Website: {brand_url}
- Description: {brand_description}

Based on this brand information, generate 2-3 ideal customer profile personas."""

        # Call OpenRouter API
        with st.spinner("Generating ICP suggestions with AI..."):
            response = client.chat.completions.create(
                model="x-ai/grok-4-fast",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "icp_suggestions",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "icps": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "role": {"type": "string"},
                                            "goals": {"type": "string"},
                                            "challenges": {"type": "string"}
                                        },
                                        "required": ["name", "role", "goals", "challenges"],
                                        "additionalProperties": False
                                    }
                                },
                                "rationale": {"type": "string"}
                            },
                            "required": ["icps", "rationale"],
                            "additionalProperties": False
                        }
                    }
                }
            )

            result = json.loads(response.choices[0].message.content)
            return result

    except Exception as e:
        st.error(f"Error generating ICP suggestions: {str(e)}")
        return None

# Button to generate suggestions
col1, col2 = st.columns([2, 1])
with col1:
    if st.button("🤖 Suggest ICPs from Brand", type="primary", use_container_width=True):
        suggestions = generate_icp_suggestions()
        if suggestions:
            st.session_state.icp_suggestions = suggestions
            st.rerun()

with col2:
    if st.session_state.icp_suggestions and st.button("Clear Suggestions", use_container_width=True):
        st.session_state.icp_suggestions = None
        st.rerun()

# Display suggestions if available
if st.session_state.icp_suggestions:
    st.success("ICP suggestions generated! Review and accept the ones you want to keep.")

    # Show rationale
    with st.expander("Why these ICPs?", expanded=False):
        st.write(st.session_state.icp_suggestions.get('rationale', 'No rationale provided'))

    # Display each suggested ICP
    for idx, icp in enumerate(st.session_state.icp_suggestions.get('icps', [])):
        with st.expander(f"🎯 {icp['name']} - {icp['role']}", expanded=True):
            st.markdown(f"**Name:** {icp['name']}")
            st.markdown(f"**Role:** {icp['role']}")
            st.markdown(f"**Goals:**")
            st.write(icp['goals'])
            st.markdown(f"**Challenges:**")
            st.write(icp['challenges'])

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✓ Accept", key=f"accept_{idx}", type="primary"):
                    # Check if ICP with same name already exists
                    with conn.session as s:
                        result = s.execute(
                            text('SELECT COUNT(*) FROM icp_personas WHERE name = :name;'),
                            {'name': icp['name']}
                        )
                        exists = result.scalar() > 0

                    if exists:
                        st.error(f"An ICP named '{icp['name']}' already exists. Please delete it first or modify the name.")
                    else:
                        # Insert the ICP
                        try:
                            with conn.session as s:
                                s.execute(text('''
                                    INSERT INTO icp_personas (name, role, goals, challenges)
                                    VALUES (:name, :role, :goals, :challenges)
                                '''), {
                                    'name': icp['name'],
                                    'role': icp['role'],
                                    'goals': icp['goals'],
                                    'challenges': icp['challenges']
                                })
                                s.commit()
                            st.success(f"✓ Added ICP: {icp['name']}")
                            # Remove this ICP from suggestions
                            st.session_state.icp_suggestions['icps'].pop(idx)
                            # Clear suggestions if all accepted
                            if not st.session_state.icp_suggestions['icps']:
                                st.session_state.icp_suggestions = None
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error adding ICP: {str(e)}")

            with col2:
                if st.button("✗ Reject", key=f"reject_{idx}", type="secondary"):
                    # Remove this ICP from suggestions
                    st.session_state.icp_suggestions['icps'].pop(idx)
                    # Clear suggestions if all rejected
                    if not st.session_state.icp_suggestions['icps']:
                        st.session_state.icp_suggestions = None
                    st.rerun()

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
