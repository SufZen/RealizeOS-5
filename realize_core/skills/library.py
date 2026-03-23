"""
Skill Library — browsable curated skill templates.

Ships 18 built-in skill templates organized by category.
Users can browse, preview, and install skills to their ventures
via the dashboard.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Built-in skill templates — curated set of useful workflows
SKILL_TEMPLATES: list[dict] = [
    # Content & Communication
    {
        "id": "content-pipeline",
        "name": "Content Pipeline",
        "category": "content",
        "description": "Multi-agent content creation with writer + reviewer flow",
        "version": "v1",
        "yaml": """name: content_pipeline
triggers:
  - write a post
  - create content
  - blog post
  - article
task_type: content
pipeline:
  - writer
  - reviewer
""",
    },
    {
        "id": "email-drafter",
        "name": "Email Drafter",
        "category": "content",
        "description": "Professional email drafting with optional Gmail send",
        "version": "v2",
        "yaml": """name: email_drafter
triggers:
  - draft email
  - write email
  - email to
task_type: content
steps:
  - id: draft
    type: agent
    agent: writer
    prompt: "Draft a professional email based on the user's request. Include subject line, greeting, body, and sign-off."
  - id: review
    type: agent
    agent: reviewer
    prompt: "Review this email draft for tone, clarity, and professionalism. Suggest improvements."
""",
    },
    {
        "id": "social-media",
        "name": "Social Media Post",
        "category": "content",
        "description": "Platform-optimized social media content creation",
        "version": "v1",
        "yaml": """name: social_media
triggers:
  - linkedin post
  - social post
  - twitter post
task_type: content
pipeline:
  - writer
  - reviewer
""",
    },
    # Research & Analysis
    {
        "id": "web-research",
        "name": "Web Research",
        "category": "research",
        "description": "Structured web research with source citations",
        "version": "v2",
        "yaml": """name: web_research
triggers:
  - research
  - find information about
  - look up
  - investigate
task_type: reasoning
steps:
  - id: search
    type: tool
    tool: web_search
    params:
      query: "{{user_message}}"
      count: 5
  - id: analyze
    type: agent
    agent: analyst
    prompt: "Analyze these search results and provide a structured summary with key findings and source citations."
""",
    },
    {
        "id": "competitor-analysis",
        "name": "Competitor Analysis",
        "category": "research",
        "description": "Web-powered competitive intelligence report",
        "version": "v2",
        "yaml": """name: competitor_analysis
triggers:
  - competitor analysis
  - competitive research
  - analyze competitor
task_type: reasoning
steps:
  - id: search
    type: tool
    tool: web_search
    params:
      query: "{{user_message}} competitor analysis market"
      count: 8
  - id: analyze
    type: agent
    agent: analyst
    prompt: "Create a competitive analysis based on the research. Include: market positioning, strengths/weaknesses, pricing, and strategic recommendations."
  - id: review
    type: agent
    agent: reviewer
    prompt: "Review this competitive analysis for accuracy, completeness, and actionable insights."
""",
    },
    {
        "id": "market-research",
        "name": "Market Research",
        "category": "research",
        "description": "TAM/SAM/SOM market analysis with data",
        "version": "v2",
        "yaml": """name: market_research
triggers:
  - market research
  - market analysis
  - market size
  - TAM SAM SOM
task_type: reasoning
steps:
  - id: search
    type: tool
    tool: web_search
    params:
      query: "{{user_message}} market size data statistics"
      count: 8
  - id: analyze
    type: agent
    agent: analyst
    prompt: "Create a market research report. Include TAM/SAM/SOM estimates, growth trends, key players, and market dynamics."
""",
    },
    # Meetings & Documents
    {
        "id": "meeting-prep",
        "name": "Meeting Preparation",
        "category": "meetings",
        "description": "Pre-meeting research and talking points",
        "version": "v2",
        "yaml": """name: meeting_prep
triggers:
  - meeting prep
  - prepare for meeting
  - meeting with
task_type: reasoning
steps:
  - id: research
    type: agent
    agent: analyst
    prompt: "Research the meeting context and participants. Prepare key talking points, questions to ask, and relevant background information."
  - id: format
    type: agent
    agent: writer
    prompt: "Format the meeting prep as a clear briefing document with sections: Objective, Key Topics, Talking Points, Questions to Ask, Background."
""",
    },
    {
        "id": "meeting-summary",
        "name": "Meeting Summary",
        "category": "meetings",
        "description": "Post-meeting recap with action items",
        "version": "v1",
        "yaml": """name: meeting_summary
triggers:
  - meeting summary
  - meeting recap
  - meeting notes
task_type: content
pipeline:
  - writer
""",
    },
    # Operations & Business
    {
        "id": "weekly-review",
        "name": "Weekly Review",
        "category": "operations",
        "description": "Weekly metrics summary with narrative and blockers",
        "version": "v1",
        "yaml": """name: weekly_review
triggers:
  - weekly review
  - weekly summary
  - week in review
task_type: reasoning
pipeline:
  - analyst
""",
    },
    {
        "id": "strategy-analysis",
        "name": "Strategy Analysis",
        "category": "operations",
        "description": "Strategic market and business model analysis",
        "version": "v1",
        "yaml": """name: strategy_analysis
triggers:
  - strategy analysis
  - strategic plan
  - business strategy
task_type: complex
pipeline:
  - analyst
  - reviewer
""",
    },
    {
        "id": "contract-review",
        "name": "Contract Review",
        "category": "operations",
        "description": "Risk flagging, clause extraction, plain-language summary",
        "version": "v1",
        "yaml": """name: contract_review
triggers:
  - review contract
  - contract review
  - analyze contract
task_type: reasoning
pipeline:
  - analyst
  - reviewer
""",
    },
    {
        "id": "budget-check",
        "name": "Budget Check",
        "category": "operations",
        "description": "Budget status and variance analysis",
        "version": "v1",
        "yaml": """name: budget_check
triggers:
  - budget check
  - budget status
  - budget variance
task_type: financial
pipeline:
  - analyst
""",
    },
    # Financial
    {
        "id": "deal-analysis",
        "name": "Deal Analysis",
        "category": "financial",
        "description": "Investment deal evaluation with scoring",
        "version": "v1",
        "yaml": """name: deal_analysis
triggers:
  - deal analysis
  - evaluate deal
  - deal review
  - investment analysis
task_type: financial
pipeline:
  - analyst
  - reviewer
""",
    },
    {
        "id": "invoice-processor",
        "name": "Invoice Processor",
        "category": "financial",
        "description": "Invoice processing through payment cycle",
        "version": "v1",
        "yaml": """name: invoice_processor
triggers:
  - process invoice
  - invoice
  - payment request
task_type: financial
pipeline:
  - analyst
""",
    },
    # Brand & Marketing
    {
        "id": "brand-audit",
        "name": "Brand Audit",
        "category": "marketing",
        "description": "Online brand presence consistency check",
        "version": "v2",
        "yaml": """name: brand_audit
triggers:
  - brand audit
  - brand review
  - brand consistency
task_type: reasoning
steps:
  - id: search
    type: tool
    tool: web_search
    params:
      query: "{{user_message}} brand presence online"
      count: 5
  - id: analyze
    type: agent
    agent: analyst
    prompt: "Analyze the brand's online presence. Check for consistency across platforms, messaging alignment, and visual identity coherence."
""",
    },
    {
        "id": "seo-content",
        "name": "SEO Content Pipeline",
        "category": "marketing",
        "description": "SEO-optimized content with keyword research",
        "version": "v2",
        "yaml": """name: seo_content
triggers:
  - seo content
  - seo article
  - optimize for seo
task_type: content
steps:
  - id: keywords
    type: tool
    tool: web_search
    params:
      query: "{{user_message}} keywords SEO"
      count: 5
  - id: write
    type: agent
    agent: writer
    prompt: "Write SEO-optimized content using the keyword research. Include: title tag, meta description, H1/H2 structure, and naturally integrated keywords."
  - id: review
    type: agent
    agent: reviewer
    prompt: "Review for SEO best practices, readability, and E-E-A-T compliance."
""",
    },
    # Investor Relations
    {
        "id": "investor-deck",
        "name": "Investor Deck",
        "category": "financial",
        "description": "LP/investor presentation with portfolio data",
        "version": "v1",
        "yaml": """name: investor_deck
triggers:
  - investor deck
  - LP report
  - investor update
  - quarterly report
task_type: complex
pipeline:
  - analyst
  - writer
  - reviewer
""",
    },
    {
        "id": "presentation-generator",
        "name": "Presentation Generator",
        "category": "content",
        "description": "Structured presentation outline with key slides",
        "version": "v1",
        "yaml": """name: presentation_generator
triggers:
  - create presentation
  - slide deck
  - presentation
task_type: content
pipeline:
  - writer
  - reviewer
""",
    },
]


def get_library() -> list[dict]:
    """Get all skill templates from the library with parsed metadata."""
    import yaml as _yaml

    results = []
    for s in SKILL_TEMPLATES:
        # Parse triggers and task_type from the embedded YAML
        triggers = []
        task_type = "general"
        steps = 0
        try:
            parsed = _yaml.safe_load(s.get("yaml", ""))
            if isinstance(parsed, dict):
                triggers = parsed.get("triggers", [])
                task_type = parsed.get("task_type", "general")
                step_list = parsed.get("steps") or parsed.get("pipeline") or []
                steps = len(step_list)
        except Exception:
            pass
        results.append(
            {
                "id": s["id"],
                "name": s["name"],
                "category": s["category"],
                "description": s["description"],
                "version": s["version"],
                "task_type": task_type,
                "triggers": triggers,
                "steps": steps,
            }
        )
    return results


def get_skill_template(skill_id: str) -> dict | None:
    """Get a specific skill template by ID, including YAML content."""
    for s in SKILL_TEMPLATES:
        if s["id"] == skill_id:
            return s
    return None


def get_categories() -> list[str]:
    """Get unique skill categories."""
    return sorted(set(s["category"] for s in SKILL_TEMPLATES))


def install_skill(skill_id: str, kb_path: Path, system_config: dict) -> dict:
    """
    Install a skill template to a venture's skills directory.

    Args:
        skill_id: The template skill ID
        kb_path: Root KB path
        system_config: Venture system configuration

    Returns:
        {installed: bool, path: str, error: str}
    """
    template = get_skill_template(skill_id)
    if not template:
        return {"installed": False, "error": f"Skill '{skill_id}' not found in library"}

    routines_dir = system_config.get("routines_dir", "")
    if not routines_dir:
        return {"installed": False, "error": "Venture has no routines directory configured"}

    skills_dir = kb_path / routines_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{skill_id.replace('-', '_')}.yaml"
    target = skills_dir / filename

    if target.exists():
        return {"installed": False, "error": f"Skill '{filename}' already exists"}

    target.write_text(template["yaml"], encoding="utf-8")

    # Trigger skill reload
    try:
        from realize_core.skills.detector import reload_skills

        reload_skills(kb_path=str(kb_path))
    except Exception:
        pass

    return {
        "installed": True,
        "path": str(target.relative_to(kb_path)),
        "name": template["name"],
    }
