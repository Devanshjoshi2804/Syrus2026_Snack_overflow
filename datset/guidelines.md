# OnboardAI Implementation Guidelines

## Product Guardrails

- Stay grounded in the provided knowledge base. Do not invent company processes or contacts.
- If retrieval confidence is low, abstain and route the user to the correct human contact.
- Personalization should be deterministic first, model-assisted second.
- External integrations are bonus features; the onboarding flow must still work in mock mode.

## Demo Guardrails

- Prefer one polished path over many partially working paths.
- Keep terminal automation deterministic and verifiable.
- Treat browser automation as optional and failure-tolerant.
- Always show verification evidence for completed automated tasks.

## Engineering Guardrails

- Use `python3.11` for the project runtime.
- Keep the content files as the canonical dataset and parse them into structured models.
- Default development mode should not require any paid API or hosted LLM.
- If Ollama is available, it can improve phrasing, but the system must remain functional without it.

## Acceptance Criteria for the Hackathon MVP

1. A new hire can introduce themselves in chat.
2. The system identifies a matching persona from the provided dataset.
3. The system builds a personalized checklist.
4. The system answers knowledge questions with source grounding.
5. The system can complete at least one environment task automatically.
6. The system generates a structured HR completion report artifact.

---

*Document ID: KB-012*
*Last Updated: March 2026*
*Owner: Hackathon Build Team*
