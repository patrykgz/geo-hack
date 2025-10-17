import streamlit as st
from sqlalchemy import text
import json
from datetime import datetime
from openai import OpenAI

# Database connection
conn = st.connection('data_db', type='sql', connect_args={
    "auth_token": st.secrets.get('TURSO_DB_KEY'),
},)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=st.secrets.get("OPENAI_API_KEY") or "",
)

# Initialize database tables
with conn.session as s:
    # Recommendation sessions table
    s.execute(text('''
        CREATE TABLE IF NOT EXISTS recommendation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP NOT NULL,
            brand_name TEXT,
            data_snapshot TEXT
        );
    '''))

    # Recommendation actions table
    s.execute(text('''
        CREATE TABLE IF NOT EXISTS recommendation_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            action_name TEXT NOT NULL,
            rationale TEXT,
            target_icps TEXT,
            priority INTEGER,
            FOREIGN KEY (session_id) REFERENCES recommendation_sessions(id)
        );
    '''))

    # Recommendation examples table
    s.execute(text('''
        CREATE TABLE IF NOT EXISTS recommendation_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id INTEGER NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            targeting_notes TEXT,
            FOREIGN KEY (action_id) REFERENCES recommendation_actions(id)
        );
    '''))

    s.commit()

st.set_page_config(page_title="Recommendations", page_icon="💡")

# Define allowed actions
ALLOWED_ACTIONS = [
    {
        "id": "linkedin_posts",
        "name": "LinkedIn Thought Leadership Posts",
        "description": "Professional posts to establish authority and engage with your target audience"
    },
    {
        "id": "blog_content",
        "name": "Blog Content Ideas",
        "description": "Long-form content addressing ICP pain points and showcasing expertise"
    },
    {
        "id": "guest_posting",
        "name": "Guest Posting Opportunities",
        "description": "Target blogs and domains for guest articles to expand reach"
    },
    {
        "id": "email_campaigns",
        "name": "Email Campaign Ideas",
        "description": "Email sequences for nurturing leads and engaging prospects"
    },
    {
        "id": "content_partnerships",
        "name": "Content Partnership Targets",
        "description": "Collaborate with cited domains and publications for mutual benefit"
    },
    {
        "id": "social_media_threads",
        "name": "Social Media Thread Concepts",
        "description": "Twitter/LinkedIn threads on key topics to drive engagement"
    }
]

# Helper functions
def load_brand_info():
    """Load brand information from database"""
    with conn.session as s:
        result = s.execute(text('SELECT name, url, description FROM brand_info WHERE id = 1;'))
        row = result.fetchone()
        if row:
            return {
                "name": row[0],
                "url": row[1],
                "description": row[2]
            }
    return None

def load_icp_personas():
    """Load all ICP personas from database"""
    with conn.session as s:
        result = s.execute(text('SELECT name, role, goals, challenges FROM icp_personas;'))
        rows = result.fetchall()
        return [
            {
                "name": row[0],
                "role": row[1],
                "goals": row[2],
                "challenges": row[3]
            }
            for row in rows
        ]

def load_sample_chats(limit=20):
    """Load sample chat conversations"""
    with conn.session as s:
        result = s.execute(text('SELECT user, assistant, model FROM peec_chats LIMIT :limit;'), {'limit': limit})
        rows = result.fetchall()
        return [
            {
                "user_question": row[0],
                "assistant_response": row[1],
                "model": row[2]
            }
            for row in rows
        ]

def load_top_domains(limit=20):
    """Load top domains by citations"""
    with conn.session as s:
        result = s.execute(text('SELECT domain, type, percent, citiatons FROM peec_domains ORDER BY citiatons DESC LIMIT :limit;'), {'limit': limit})
        rows = result.fetchall()
        return [
            {
                "domain": row[0],
                "type": row[1],
                "usage_percent": row[2],
                "avg_citations": row[3]
            }
            for row in rows
        ]

def get_data_counts():
    """Get counts of available data"""
    with conn.session as s:
        icp_count = s.execute(text('SELECT COUNT(*) FROM icp_personas;')).scalar()
        chat_count = s.execute(text('SELECT COUNT(*) FROM peec_chats;')).scalar()
        domain_count = s.execute(text('SELECT COUNT(*) FROM peec_domains;')).scalar()

    return {
        "icps": icp_count,
        "chats": chat_count,
        "domains": domain_count
    }

def call_strategic_selector(data, api_key):
    """Stage 1: Strategic Selector Agent - selects 3-5 actions from allowed list"""
    system_prompt = """You are a strategic marketing advisor. Your task is to analyze the provided brand, ICP, chat, and domain data, then select 3-5 most relevant marketing actions from the allowed actions list.

For each selected action, provide:
1. A clear rationale explaining why this action is valuable based on the data
2. Which ICP personas would benefit most
3. A priority ranking (1 being highest priority)

Only select action_ids from the allowed actions list provided. Select between 3 and 5 actions."""

    user_prompt = f"""Analyze this data and select the most impactful marketing actions:

BRAND:
{json.dumps(data['brand'], indent=2)}

ICP PERSONAS:
{json.dumps(data['icps'], indent=2)}

SAMPLE CHAT CONVERSATIONS (showing common questions/topics):
{json.dumps(data['chats'][:10], indent=2)}

TOP CITED DOMAINS:
{json.dumps(data['domains'][:15], indent=2)}

ALLOWED ACTIONS TO CHOOSE FROM:
{json.dumps(ALLOWED_ACTIONS, indent=2)}

Select 3-5 actions and provide your analysis."""

    # Structured output schema for reliable JSON
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "strategic_recommendations",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "selected_actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action_id": {"type": "string"},
                                "rationale": {"type": "string"},
                                "target_icps": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "priority": {"type": "number"}
                            },
                            "required": ["action_id", "rationale", "target_icps", "priority"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["selected_actions"],
                "additionalProperties": False
            }
        }
    }

    # Log request
    print("=" * 80)
    print("STRATEGIC SELECTOR REQUEST")
    print("=" * 80)
    print(f"Model: gpt-5")
    print(f"System prompt length: {len(system_prompt)} chars")
    print(f"User prompt length: {len(user_prompt)} chars")

    response = client.chat.completions.create(
        model="openai/gpt-5",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format=response_format
    )

    # Log response
    print("=" * 80)
    print("STRATEGIC SELECTOR RESPONSE")
    print("=" * 80)
    print("Full response dump:")
    print(response.model_dump_json(indent=2))
    print("=" * 80)

    # Store in session state for debug UI
    if 'llm_logs' not in st.session_state:
        st.session_state.llm_logs = []

    st.session_state.llm_logs.append({
        'timestamp': datetime.now().isoformat(),
        'agent': 'Strategic Selector',
        'model': 'gpt-5',
        'request': {
            'system_prompt': system_prompt[:500] + '...',
            'user_prompt': user_prompt[:500] + '...'
        },
        'response': response.model_dump_json(indent=2)
    })

    # Check for empty response
    if not response.choices or not response.choices[0].message.content:
        raise ValueError("Empty response from OpenAI API")

    return response.choices[0].message.content

def call_content_generator(data, action_info, api_key):
    """Stage 2: Content Generator Agent - generates 2-4 examples for a specific action"""
    action_def = next((a for a in ALLOWED_ACTIONS if a['id'] == action_info['action_id']), None)
    action_id = action_info['action_id']

    # Action-specific system prompts for better results
    if action_id == 'blog_content':
        system_prompt = f"""You are an expert blog content writer. Your task is to write 2-3 COMPLETE blog post articles (not outlines or summaries).

ACTION: {action_def['name']}
STRATEGIC RATIONALE: {action_info['rationale']}
TARGET ICPS: {', '.join(action_info['target_icps'])}

CRITICAL INSTRUCTIONS:
- Write the ACTUAL blog post content, ready to publish
- Each blog post should be 800-1500 words minimum
- Use markdown formatting (headers, lists, bold, etc.)
- Include: compelling introduction, 3-5 detailed sections, and strong conclusion
- Reference specific pain points from the ICP data
- Mention relevant domains/sources from the data where appropriate
- Add SEO-friendly headers and natural keyword integration
- DO NOT write a summary or description of what the blog should be - write the actual content
- DO NOT write meta-instructions like "This post should include..." - just write the post itself

Generate 2-3 complete, ready-to-publish blog articles."""

    elif action_id == 'linkedin_posts':
        system_prompt = f"""You are an expert LinkedIn content strategist. Your task is to write 2-4 COMPLETE LinkedIn posts (not descriptions of posts).

ACTION: {action_def['name']}
STRATEGIC RATIONALE: {action_info['rationale']}
TARGET ICPS: {', '.join(action_info['target_icps'])}

CRITICAL INSTRUCTIONS:
- Write the ACTUAL post text that can be copy-pasted directly to LinkedIn
- Each post should be 150-300 words (LinkedIn optimal length)
- Include a hook in the first line, valuable insights in the body, and a call-to-action
- Use line breaks for readability (max 2-3 sentences per paragraph)
- Make it conversational and engaging
- Reference specific insights from ICP challenges or chat data
- DO NOT write "This post should talk about..." - write the actual post text
- You may use emojis if appropriate for the brand voice

Generate 2-4 complete, ready-to-post LinkedIn posts."""

    elif action_id == 'email_campaigns':
        system_prompt = f"""You are an expert email copywriter. Your task is to write 2-4 COMPLETE email messages (not outlines).

ACTION: {action_def['name']}
STRATEGIC RATIONALE: {action_info['rationale']}
TARGET ICPS: {', '.join(action_info['target_icps'])}

CRITICAL INSTRUCTIONS:
- Write the ACTUAL email content including subject line and body
- Format each example as: Subject line, then email body
- Keep emails concise (200-400 words)
- Personalize to the ICP's role, goals, and challenges
- Include a clear call-to-action
- Use compelling subject lines (under 50 characters)
- DO NOT write "This email should address..." - write the actual email
- Make it sound natural and personal, not salesy

Generate 2-4 complete, ready-to-send email campaigns."""

    elif action_id == 'guest_posting':
        system_prompt = f"""You are an expert at guest post pitching. Your task is to create 2-3 COMPLETE pitch packages.

ACTION: {action_def['name']}
STRATEGIC RATIONALE: {action_info['rationale']}
TARGET ICPS: {', '.join(action_info['target_icps'])}

CRITICAL INSTRUCTIONS:
- For each example, provide TWO parts: 1) Pitch email to the publication, 2) Article outline
- The pitch email should be 150-250 words, persuasive and specific
- Identify specific high-authority domains from the data to target
- The article outline should include title, introduction summary, 4-6 key sections with bullet points
- Explain why this topic fits the publication's audience
- DO NOT write "Pitch publications that..." - write actual pitch emails
- Reference the brand's expertise and value proposition

Generate 2-3 complete guest post pitch packages (each with pitch email + article outline)."""

    elif action_id == 'social_media_threads':
        system_prompt = f"""You are an expert at creating viral social media threads. Your task is to write 2-4 COMPLETE threads.

ACTION: {action_def['name']}
STRATEGIC RATIONALE: {action_info['rationale']}
TARGET ICPS: {', '.join(action_info['target_icps'])}

CRITICAL INSTRUCTIONS:
- Write the ACTUAL thread text for Twitter/X or LinkedIn
- Each thread should be 5-10 tweets/posts
- Number each post (1/10, 2/10, etc.)
- First post should be a compelling hook
- Each subsequent post should build on the previous one
- Use short, punchy sentences
- Include insights from ICP challenges or chat data
- End with a strong call-to-action
- DO NOT write "This thread should cover..." - write the actual thread
- Keep each post under 280 characters if for Twitter

Generate 2-4 complete, ready-to-post social media threads."""

    elif action_id == 'content_partnerships':
        system_prompt = f"""You are an expert at forming content partnerships. Your task is to create 2-3 COMPLETE partnership proposals.

ACTION: {action_def['name']}
STRATEGIC RATIONALE: {action_info['rationale']}
TARGET ICPS: {', '.join(action_info['target_icps'])}

CRITICAL INSTRUCTIONS:
- For each example, provide: 1) Target partner (specific domain from data), 2) Outreach email, 3) Collaboration idea
- The outreach email should be 200-300 words, professional and value-focused
- Propose specific, mutually beneficial collaboration ideas
- Reference why this partnership makes sense based on their content/audience
- Include clear next steps
- DO NOT write "Reach out to partners who..." - identify specific partners and write actual outreach
- Make it personalized and compelling

Generate 2-3 complete partnership proposals (each with target, email, and collaboration idea)."""

    else:
        # Fallback for any other action types
        system_prompt = f"""You are an expert marketing content creator. Your task is to generate 2-4 concrete, ready-to-use examples for the following marketing action:

ACTION: {action_def['name']}
DESCRIPTION: {action_def['description']}
STRATEGIC RATIONALE: {action_info['rationale']}
TARGET ICPS: {', '.join(action_info['target_icps'])}

CRITICAL: Write the ACTUAL content, not a description or outline of what the content should be.

Create examples that are:
1. Specific and actionable (not generic templates)
2. Tailored to the brand and ICP personas
3. Reference insights from the chat data and domain analysis where relevant
4. Professional and compelling
5. Ready to use immediately without further editing

Generate between 2 and 4 high-quality, complete examples."""

    # Adjust example count based on action type
    if action_id == 'blog_content':
        example_count = 2  # Blog posts are long, so generate fewer
    elif action_id in ['linkedin_posts', 'email_campaigns', 'social_media_threads']:
        example_count = min(3, len(action_info.get('target_icps', [])) + 1)
    else:
        example_count = 2 if len(action_info.get('target_icps', [])) <= 2 else 3

    user_prompt = f"""Generate {example_count} COMPLETE, READY-TO-USE examples based on this context:

BRAND:
{json.dumps(data['brand'], indent=2)}

ICP PERSONAS (these are your target audience):
{json.dumps(data['icps'], indent=2)}

SAMPLE CHAT CONVERSATIONS (real questions/topics from potential customers):
{json.dumps(data['chats'][:10], indent=2)}

TOP CITED DOMAINS (authoritative sources in this space):
{json.dumps(data['domains'][:15], indent=2)}

REMEMBER: Write the actual {action_def['name'].lower()}, NOT a description of what to write.
The output should be immediately usable without any additional work.

Create {example_count} high-quality examples now."""

    # Structured output schema for reliable JSON
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "content_examples",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "examples": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "content": {"type": "string"},
                                "targeting_notes": {"type": "string"}
                            },
                            "required": ["title", "content", "targeting_notes"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["examples"],
                "additionalProperties": False
            }
        }
    }

    # Log request
    print("=" * 80)
    print(f"CONTENT GENERATOR REQUEST: {action_def['name']}")
    print("=" * 80)
    print(f"Model: x-ai/grok-4-fast")
    print(f"Action: {action_info['action_id']}")
    print(f"System prompt length: {len(system_prompt)} chars")
    print(f"User prompt length: {len(user_prompt)} chars")

    response = client.chat.completions.create(
        model="x-ai/grok-4-fast",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format=response_format
    )

    # Log response
    print("=" * 80)
    print(f"CONTENT GENERATOR RESPONSE: {action_def['name']}")
    print("=" * 80)
    print("Full response dump:")
    print(response.model_dump_json(indent=2))
    print("=" * 80)

    # Store in session state for debug UI
    if 'llm_logs' not in st.session_state:
        st.session_state.llm_logs = []

    st.session_state.llm_logs.append({
        'timestamp': datetime.now().isoformat(),
        'agent': f'Content Generator ({action_def["name"]})',
        'model': 'gpt-5',
        'request': {
            'action': action_info['action_id'],
            'system_prompt': system_prompt[:500] + '...',
            'user_prompt': user_prompt[:500] + '...'
        },
        'response': response.model_dump_json(indent=2)
    })

    # Check for empty response
    if not response.choices or not response.choices[0].message.content:
        raise ValueError("Empty response from OpenAI API")

    return response.choices[0].message.content

def generate_recommendations():
    """Main orchestration function"""
    # Get API key
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key or api_key == "your-openai-api-key-here":
        st.error("OpenAI API key not configured. Please add your API key to .streamlit/secrets.toml")
        return False

    # Load all data
    with st.spinner("Loading data from database..."):
        brand = load_brand_info()
        icps = load_icp_personas()
        chats = load_sample_chats(limit=20)
        domains = load_top_domains(limit=20)

        if not brand:
            st.error("No brand information found. Please configure your brand on the main page first.")
            return False

        if len(icps) == 0:
            st.error("No ICP personas found. Please add at least one ICP persona.")
            return False

        data = {
            "brand": brand,
            "icps": icps,
            "chats": chats,
            "domains": domains
        }

    # Stage 1: Strategic Selector
    with st.spinner("🧠 Analyzing your brand and audience data..."):
        try:
            selector_response = call_strategic_selector(data, api_key)

            if not selector_response:
                st.error("Empty response from strategic selector agent. Check debug logs below.")
                return False

            selected_actions = json.loads(selector_response)

            if 'selected_actions' not in selected_actions:
                st.error("Invalid response from strategic selector agent - missing 'selected_actions' key")
                st.code(selector_response)
                return False

            actions = selected_actions['selected_actions']

            if len(actions) == 0:
                st.error("Strategic selector returned zero actions")
                return False

            if len(actions) < 3 or len(actions) > 5:
                st.warning(f"Expected 3-5 actions, got {len(actions)}. Proceeding anyway...")

            # Validate action IDs
            valid_ids = {a['id'] for a in ALLOWED_ACTIONS}
            for action in actions:
                if action['action_id'] not in valid_ids:
                    st.error(f"Invalid action_id: {action['action_id']}. Must be one of: {', '.join(valid_ids)}")
                    return False

        except json.JSONDecodeError as e:
            st.error(f"Failed to parse strategic selector response: {str(e)}")
            if 'selector_response' in locals():
                st.code(selector_response[:1000] if len(selector_response) > 1000 else selector_response)
            st.info("Check the Debug section below for full API logs")
            return False
        except ValueError as e:
            st.error(f"OpenAI API error: {str(e)}")
            st.info("Check the Debug section below for full API logs")
            return False
        except Exception as e:
            st.error(f"Unexpected error in strategic selector: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
            return False

    # Create session
    with conn.session as s:
        result = s.execute(text('''
            INSERT INTO recommendation_sessions (created_at, brand_name, data_snapshot)
            VALUES (:created_at, :brand_name, :data_snapshot)
        '''), {
            'created_at': datetime.now().isoformat(),
            'brand_name': brand['name'],
            'data_snapshot': json.dumps({
                'icp_count': len(icps),
                'chat_count': len(chats),
                'domain_count': len(domains)
            })
        })
        s.commit()
        session_id = result.lastrowid

    # Stage 2: Content Generators
    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, action in enumerate(actions):
        action_def = next((a for a in ALLOWED_ACTIONS if a['id'] == action['action_id']), None)
        status_text.text(f"✍️ Generating {action_def['name']}... ({idx + 1}/{len(actions)})")

        try:
            generator_response = call_content_generator(data, action, api_key)

            if not generator_response:
                st.warning(f"Empty response for {action_def['name']}. Skipping...")
                continue

            examples_data = json.loads(generator_response)

            if 'examples' not in examples_data:
                st.warning(f"No 'examples' key in response for {action_def['name']}. Skipping...")
                continue

            examples = examples_data['examples']

            if len(examples) == 0:
                st.warning(f"No examples generated for {action_def['name']}. Skipping...")
                continue

            # Save action
            with conn.session as s:
                result = s.execute(text('''
                    INSERT INTO recommendation_actions
                    (session_id, action_type, action_name, rationale, target_icps, priority)
                    VALUES (:session_id, :action_type, :action_name, :rationale, :target_icps, :priority)
                '''), {
                    'session_id': session_id,
                    'action_type': action['action_id'],
                    'action_name': action_def['name'],
                    'rationale': action['rationale'],
                    'target_icps': json.dumps(action['target_icps']),
                    'priority': action.get('priority', 99)
                })
                s.commit()
                action_db_id = result.lastrowid

                # Save examples
                for example in examples:
                    s.execute(text('''
                        INSERT INTO recommendation_examples (action_id, title, content, targeting_notes)
                        VALUES (:action_id, :title, :content, :targeting_notes)
                    '''), {
                        'action_id': action_db_id,
                        'title': example.get('title', 'Untitled'),
                        'content': example['content'],
                        'targeting_notes': example.get('targeting_notes', '')
                    })
                s.commit()

        except json.JSONDecodeError as e:
            st.warning(f"Failed to parse JSON for {action_def['name']}: {str(e)}")
            st.caption("Check debug logs for details")
            continue
        except ValueError as e:
            st.warning(f"API error for {action_def['name']}: {str(e)}")
            st.caption("Check debug logs for details")
            continue
        except Exception as e:
            st.warning(f"Unexpected error generating {action_def['name']}: {str(e)}")
            st.caption("Check debug logs for details")
            continue

        progress_bar.progress((idx + 1) / len(actions))

    status_text.text("✅ Recommendations generated successfully!")
    progress_bar.empty()

    return True

# Main UI
st.markdown("# AI Marketing Recommendations 💡")
st.markdown("Generate personalized marketing recommendations based on your brand, ICP personas, and market data.")

# Data status panel
st.markdown("## Available Data")

brand = load_brand_info()
counts = get_data_counts()

col1, col2, col3, col4 = st.columns(4)

with col1:
    if brand:
        st.metric("Brand", "✅")
    else:
        st.metric("Brand", "❌")

with col2:
    st.metric("ICP Personas", counts['icps'])

with col3:
    st.metric("Chat Samples", counts['chats'])

with col4:
    st.metric("Domains", counts['domains'])

# Validation
can_generate = brand is not None and counts['icps'] > 0

if not can_generate:
    if not brand:
        st.warning("⚠️ Please configure your brand information on the main page before generating recommendations.")
    if counts['icps'] == 0:
        st.warning("⚠️ Please add at least one ICP persona on the ICP Profiles page before generating recommendations.")

# Generate button
st.markdown("---")

if st.button("🚀 Generate Recommendations", type="primary", disabled=not can_generate):
    success = generate_recommendations()
    if success:
        st.balloons()
        st.rerun()

# Display latest recommendations
st.markdown("---")
st.markdown("## Latest Recommendations")

with conn.session as s:
    # Get latest session
    session_result = s.execute(text('''
        SELECT id, created_at, brand_name
        FROM recommendation_sessions
        ORDER BY created_at DESC
        LIMIT 1
    '''))
    latest_session = session_result.fetchone()

    if latest_session:
        session_id = latest_session[0]
        st.caption(f"Generated on {latest_session[1][:19]} for {latest_session[2]}")

        # Get all actions for this session
        actions_result = s.execute(text('''
            SELECT id, action_type, action_name, rationale, target_icps, priority
            FROM recommendation_actions
            WHERE session_id = :session_id
            ORDER BY priority ASC
        '''), {'session_id': session_id})
        actions = actions_result.fetchall()

        if actions:
            # Create tabs for each action
            tab_labels = [f"{i+1}. {action[2]}" for i, action in enumerate(actions)]
            tabs = st.tabs(tab_labels)

            for tab, action in zip(tabs, actions):
                with tab:
                    action_db_id = action[0]
                    action_type = action[1]
                    action_name = action[2]
                    rationale = action[3]
                    target_icps = json.loads(action[4]) if action[4] else []

                    # Show rationale
                    st.markdown("### 🎯 Strategic Rationale")
                    st.info(rationale)

                    if target_icps:
                        st.markdown(f"**Target ICPs:** {', '.join(target_icps)}")

                    # Get examples
                    examples_result = s.execute(text('''
                        SELECT title, content, targeting_notes
                        FROM recommendation_examples
                        WHERE action_id = :action_id
                    '''), {'action_id': action_db_id})
                    examples = examples_result.fetchall()

                    st.markdown("### 📝 Examples")

                    for idx, example in enumerate(examples, 1):
                        with st.expander(f"Example {idx}: {example[0]}", expanded=(idx == 1)):
                            st.markdown("**Content:**")
                            st.markdown(example[1])

                            if example[2]:
                                st.markdown("**Why this works:**")
                                st.caption(example[2])
        else:
            st.info("No recommendations found in this session.")
    else:
        st.info("No recommendations generated yet. Click 'Generate Recommendations' to get started!")

# Debug section
st.markdown("---")
with st.expander("🔍 Debug: LLM Call Logs"):
    if 'llm_logs' in st.session_state and st.session_state.llm_logs:
        st.markdown(f"**Total API Calls:** {len(st.session_state.llm_logs)}")

        for idx, log in enumerate(reversed(st.session_state.llm_logs), 1):
            st.markdown(f"### Call {idx}: {log['agent']}")
            st.caption(f"Timestamp: {log['timestamp']}")
            st.caption(f"Model: {log['model']}")

            with st.expander("Request Details"):
                if 'action' in log['request']:
                    st.write(f"**Action:** {log['request']['action']}")
                st.write("**System Prompt (first 500 chars):**")
                st.code(log['request']['system_prompt'])
                st.write("**User Prompt (first 500 chars):**")
                st.code(log['request']['user_prompt'])

            with st.expander("Full Response Dump"):
                st.code(log['response'], language='json')

            st.markdown("---")

        if st.button("Clear Logs"):
            st.session_state.llm_logs = []
            st.rerun()
    else:
        st.info("No LLM calls logged yet. Generate recommendations to see API call logs here.")
