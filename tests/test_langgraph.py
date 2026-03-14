from __future__ import annotations

from onboardai.config import AppConfig
from onboardai.graph import OnboardingEngine, build_langgraph
from onboardai.models import OnboardingState


def test_build_langgraph_compiles(project_root):
    """Ensure the full LangGraph with all nodes compiles without error."""
    try:
        import langgraph  # noqa: F401
    except ImportError:
        return  # langgraph not installed, skip test
    config = AppConfig(project_root=project_root)
    engine = OnboardingEngine(config)
    compiled = build_langgraph(engine)
    assert compiled is not None


def test_langgraph_routes_intake_for_new_user(project_root):
    """First message from a new user should route to intake node."""
    config = AppConfig(project_root=project_root)
    engine = OnboardingEngine(config)
    compiled = build_langgraph(engine)
    if compiled is None:
        return  # langgraph not installed

    state = engine.new_state()
    result = compiled.invoke({
        "state": state,
        "message": "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    })
    assert "Welcome Riya" in result["response"]
    assert "Step 1: `C-01`" in result["response"]
    assert result["state"].employee_profile is not None


def test_langgraph_routes_question_to_rag(project_root):
    """A question from an onboarded user should route to rag_qa node."""
    config = AppConfig(project_root=project_root)
    engine = OnboardingEngine(config)
    compiled = build_langgraph(engine)
    if compiled is None:
        return

    state = engine.new_state()
    engine.handle_message(state, "Hi, I'm Riya. Backend Intern, Node.js.")

    result = compiled.invoke({
        "state": state,
        "message": "What is the dress code policy?",
    })
    # Should get a response (either grounded answer or abstention)
    assert result["response"]
    assert len(result["response"]) > 10
