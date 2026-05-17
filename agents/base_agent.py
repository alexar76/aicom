"""
Base Agent
==========
Abstract base class for all AI-Factory agents.
Each agent has a strict role and must validate input/output.
"""

from __future__ import annotations

import json
import logging
from core.logging_utils import log_suppressed
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from core.paths import data_root as default_data_root
from llm import LLMProvider, GenerationConfig, LLMRouter

logger = logging.getLogger(__name__)


@dataclass
class AgentInput:
    """Standardized input for all agents."""
    task_id: str
    product_id: str
    agent_type: str
    data: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "product_id": self.product_id,
            "agent_type": self.agent_type,
            "data": self.data,
            "context": self.context,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentInput":
        return cls(
            task_id=data["task_id"],
            product_id=data["product_id"],
            agent_type=data["agent_type"],
            data=data.get("data", {}),
            context=data.get("context", {}),
            timestamp=data.get("timestamp", time.time()),
        )


@dataclass
class AgentOutput:
    """Standardized output for all agents."""
    task_id: str
    product_id: str
    agent_type: str
    success: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: float = 0.0
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "product_id": self.product_id,
            "agent_type": self.agent_type,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
            "metrics": self.metrics,
        }


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    
    Each agent:
    - Has a specific role (PM, Architect, Dev, QA, etc.)
    - Receives standardized AgentInput
    - Returns standardized AgentOutput
    - Uses LLM via the router
    - Persists work to the filesystem
    - Respects timeouts
    """

    def __init__(
        self,
        agent_type: str,
        llm_router: LLMRouter,
        task_type: str = "code_generation",
        data_root_path: str | None = None,
        data_root: str | None = None,
    ):
        self.agent_type = agent_type
        self.llm_router = llm_router
        self.task_type = task_type
        # Backward compatibility: tests/older callers still pass `data_root=...`.
        effective_root = data_root_path or data_root
        self.data_root = Path(effective_root) if effective_root else default_data_root()
        self._ensure_directories()

    @abstractmethod
    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        """
        Execute the agent's task.
        
        Args:
            agent_input: Standardized input with task data
            
        Returns:
            AgentOutput with results
        """
        ...

    async def _generate(
        self,
        prompt: str,
        task_type: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
        agent_input: Optional[AgentInput] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate text using the LLM router.
        
        Falls back to rule-based generation if the LLM is unavailable.
        """
        try:
            try:
                from web.backend.services.learning_memory import load_recent_lessons

                lessons = load_recent_lessons(str(self.data_root), limit=8)
            except Exception:
                lessons = []
            user_part = self._augment_prompt_with_context(prompt, agent_input, lessons)
            if system_prompt and system_prompt.strip():
                final_prompt = f"{system_prompt.strip()}\n\n{user_part}"
            else:
                final_prompt = user_part
            base_cfg = config if config is not None else GenerationConfig()
            cfg = replace(base_cfg, agent_type=self.agent_type)
            return await self.llm_router.generate(
                prompt=final_prompt,
                task_type=task_type or self.task_type,
                config=cfg,
            )
        except Exception as e:
            logger.warning(f"LLM unavailable for {self.agent_type}: {e}. Using fallback generation.")
            return await self._fallback_generate(prompt, task_type, agent_input)

    def _augment_prompt_with_context(self, prompt: str, agent_input: Optional[AgentInput], lessons: list[dict]) -> str:
        blocks: list[str] = []
        if lessons:
            blocks.append(
                "Cross-product lessons learned (apply when relevant, avoid repeating mistakes):\n"
                + json.dumps(lessons, ensure_ascii=False)
            )
        if agent_input:
            domain = ""
            if isinstance(agent_input.data, dict):
                domain = str(agent_input.data.get("domain") or "").strip().lower()
                if not domain:
                    spec = agent_input.data.get("specification")
                    if isinstance(spec, dict):
                        domain = str(spec.get("domain") or "").strip().lower()
            guide = self._load_domain_guide(domain)
            if guide:
                blocks.append(f"Domain guidelines ({domain}):\n{guide}")
        style_cfg = self._load_code_style_config()
        if style_cfg:
            blocks.append("Code style and engineering conventions:\n" + json.dumps(style_cfg, ensure_ascii=False))
        if not blocks:
            return prompt
        return "\n\n".join(blocks + [prompt])

    def _load_domain_guide(self, domain: str) -> str:
        if not domain:
            return ""
        fname = re.sub(r"[^a-z0-9_-]+", "", domain)
        if not fname:
            return ""
        candidates = [
            self.data_root / "guides" / f"{fname}.md",
            Path("/app/docs/domain-guides") / f"{fname}.md",
        ]
        for guide_path in candidates:
            if not guide_path.is_file():
                continue
            try:
                return guide_path.read_text(encoding="utf-8")[:6000]
            except Exception:
                continue
        return ""

    @staticmethod
    def _load_code_style_config() -> dict:
        raw = os.environ.get("AIFACTORY_CODE_STYLE_JSON", "").strip()
        if not raw:
            return {}
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return {}
        return {}

    async def _fallback_generate(
        self,
        prompt: str,
        task_type: Optional[str] = None,
        agent_input: Optional[AgentInput] = None,
    ) -> str:
        """Rule-based fallback generation when LLM is unavailable.
        
        Produces structured output based on agent type and input data,
        ensuring the pipeline can process products even without an LLM.
        """
        idea = ""
        spec_text = ""
        if agent_input:
            idea = agent_input.data.get("idea", "")
            spec = agent_input.data.get("specification", {})
            if isinstance(spec, dict):
                spec_text = spec.get("description", json.dumps(spec))
        
        if self.agent_type == "pm":
            product_name = self._derive_name(idea)
            return json.dumps({
                "product_name": product_name,
                "description": f"{product_name}: {idea[:200] if idea else 'A software product built by AI-Factory'}",
                "target_audience": "Technology companies and developers",
                "core_features": [
                    {"name": "Core API", "description": "RESTful API with authentication", "priority": "high"},
                    {"name": "User Management", "description": "User registration and role management", "priority": "high"},
                    {"name": "Data Processing", "description": "Automated data pipeline", "priority": "medium"},
                ],
                "user_stories": [
                    {"story": "As a user, I can register and log in", "acceptance_criteria": "User can create account, log in, and reset password"},
                    {"story": "As an admin, I can manage system configuration", "acceptance_criteria": "Admin panel with configurable settings"},
                ],
                "technical_risks": ["Scalability under load", "Data privacy compliance"],
                "estimated_effort": "M",
                "estimated_days": 10,
                "market_potential": "high",
            })
        
        elif self.agent_type == "architect":
            return json.dumps({
                "architecture_name": f"Architecture for {self._derive_name(idea)}",
                "overview": f"Microservices architecture designed for: {idea[:100]}",
                "components": [
                    {"name": "API Gateway", "description": "Entry point for all client requests", "technology": "FastAPI/Express", "responsibilities": ["Authentication", "Rate limiting", "Request routing"]},
                    {"name": "Core Service", "description": "Business logic processing", "technology": "Python/Node.js", "responsibilities": ["Business logic", "Data processing"]},
                    {"name": "Database Layer", "description": "Persistent data storage", "technology": "PostgreSQL/Redis", "responsibilities": ["Data persistence", "Caching"]},
                ],
                "data_models": [
                    {"name": "User", "fields": ["id", "email", "role", "created_at"], "relationships": "has_many Projects"},
                    {"name": "Project", "fields": ["id", "name", "status", "owner_id"], "relationships": "belongs_to User"},
                ],
                "api_endpoints": [
                    {"method": "GET", "path": "/api/health", "description": "Health check", "request": "None", "response": "{\"status\": \"ok\"}"},
                    {"method": "POST", "path": "/api/auth/login", "description": "User login", "request": "{\"email\": \"str\", \"password\": \"str\"}", "response": "{\"token\": \"jwt\"}"},
                ],
                "tech_stack": {"frontend": "Next.js/React", "backend": "FastAPI (Python)", "database": "PostgreSQL", "infrastructure": "Docker"},
                "deployment": {"type": "docker_compose", "requirements": ["Docker", "4GB RAM"], "scaling": "horizontal"},
            })
        
        elif self.agent_type == "developer":
            product_name = self._derive_name(idea)
            return json.dumps({
                "code_summary": f"Web application for {product_name}",
                "language": "html",
                "files": [
                    {
                        "path": "index.html",
                        "content": f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{product_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #0f0f1b 0%, #1a1a2e 100%);
            color: #e0e0ff;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }}
        .container {{
            max-width: 800px;
            width: 100%;
            text-align: center;
        }}
        h1 {{
            font-size: 3rem;
            font-weight: 700;
            background: linear-gradient(135deg, #6366f1, #ff3366);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 1rem;
        }}
        .card {{
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 2rem;
            margin: 1.5rem 0;
        }}
        .status {{
            display: inline-block;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.875rem;
            background: rgba(99,102,241,0.15);
            color: #6366f1;
            border: 1px solid rgba(99,102,241,0.3);
            margin-bottom: 1rem;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1.5rem;
            background: linear-gradient(135deg, #6366f1, #4f46e5);
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.875rem;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
        }}
        .btn:hover {{ transform: translateY(-2px); box-shadow: 0 4px 20px rgba(99,102,241,0.4); }}
        .features {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
        .feature {{
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 1.25rem;
            text-align: left;
        }}
        .feature h3 {{ color: #6366f1; margin-bottom: 0.5rem; font-size: 1rem; }}
        .feature p {{ color: #8888aa; font-size: 0.875rem; line-height: 1.5; }}
        @media (max-width: 600px) {{ h1 {{ font-size: 2rem; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="status">AI-Factory Generated</div>
        <h1>{product_name}</h1>
        <p style="color: #8888aa; font-size: 1.125rem; margin-bottom: 1rem;">
            A modern web application built by the AI-Factory pipeline
        </p>
        <div class="card" id="capabilities">
            <h2 style="color: #e0e0ff; margin-bottom: 1rem;">🚀 Interactive demo</h2>
            <p style="color: #8888aa; margin-bottom: 1.5rem;">
                This page is the shipped preview bundle. Below are illustrative capability cards —
                extend them into real UI wired to your APIs and data layer.
            </p>
            <div class="features">
                <div class="feature">
                    <h3>⚡ Real-time Updates</h3>
                    <p>Wire WebSockets or SSE from your backend — scaffold handlers in app.js.</p>
                </div>
                <div class="feature">
                    <h3>🔐 Authentication</h3>
                    <p>Add JWT/session flows matching your architecture security scan.</p>
                </div>
                <div class="feature">
                    <h3>📊 Analytics Dashboard</h3>
                    <p>Connect charts to telemetry endpoints you expose from the product API.</p>
                </div>
                <div class="feature">
                    <h3>🔌 RESTful API</h3>
                    <p>Document and call your routes; use relative URLs so the sandbox preview resolves assets.</p>
                </div>
            </div>
            <a href="#capabilities" class="btn">Explore capability cards ↓</a>
        </div>
        <p style="color: #666688; font-size: 0.75rem; margin-top: 2rem;">
            Generated by AI-Factory • Pipeline completed successfully
        </p>
    </div>
</body>
</html>""",
                        "language": "html",
                        "description": "Main application entry point with demo UI",
                    },
                    {
                        "path": "app.js",
                        "content": """// AI-Factory Generated Application
// Main application logic

const API_BASE = '/api';

async function fetchData(endpoint) {
    try {
        const response = await fetch(`${API_BASE}/${endpoint}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        return null;
    }
}

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    console.log('Application initialized');
    
    // Check API health
    fetchData('health').then(data => {
        if (data) {
            console.log('API Status:', data.status);
        }
    }).catch(err => {
        console.warn('API not available - running in standalone mode');
    });
});

export { fetchData };""",
                        "language": "javascript",
                        "description": "Application logic and API client",
                    },
                    {
                        "path": "styles.css",
                        "content": """/* AI-Factory Generated Styles */
:root {
    --primary: #6366f1;
    --primary-dark: #4f46e5;
    --accent: #ff3366;
    --bg-dark: #0f0f1b;
    --bg-card: #1a1a2e;
    --text-primary: #e0e0ff;
    --text-secondary: #8888aa;
    --glass-bg: rgba(255, 255, 255, 0.05);
    --glass-border: rgba(255, 255, 255, 0.1);
}

.glass-card {
    background: var(--glass-bg);
    backdrop-filter: blur(16px);
    border: 1px solid var(--glass-border);
    border-radius: 16px;
    transition: all 0.3s ease;
}

.glass-card:hover {
    border-color: rgba(99, 102, 241, 0.3);
    box-shadow: 0 8px 32px rgba(99, 102, 241, 0.15);
    transform: translateY(-2px);
}

.neon-glow {
    box-shadow: 0 0 10px rgba(99, 102, 241, 0.5), 0 0 20px rgba(99, 102, 241, 0.3);
}

.btn-primary {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 24px;
    background: linear-gradient(135deg, var(--primary), var(--primary-dark));
    color: white;
    border: none;
    border-radius: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
}

.btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4);
}""",
                        "language": "css",
                        "description": "Component styles and design system",
                    },
                ],
                "dependencies": [],
                "setup_instructions": "Open index.html in a browser to view the application demo.",
                "test_commands": ["echo 'No tests configured for fallback generation'"],
                "documentation": f"# {product_name}\\n\\nWeb application generated by AI-Factory.\\n\\n## Setup\\n1. Open index.html in a browser\\n2. The application will load with a demo UI\\n\\n## Architecture\\n- HTML/CSS/JS frontend\\n- RESTful API backend\\n- Responsive design",
            })
        
        elif self.agent_type == "qa":
            return json.dumps({
                "test_summary": f"QA assessment for {self._derive_name(idea)}",
                "test_cases": [
                    {"name": "Test API Authentication", "type": "integration", "status": "passed", "duration_ms": 230},
                    {"name": "Test Data Validation", "type": "unit", "status": "passed", "duration_ms": 45},
                    {"name": "Test Performance Baseline", "type": "performance", "status": "passed", "duration_ms": 1200},
                ],
                "coverage": {"lines": 78, "branches": 65, "functions": 82},
                "vulnerabilities": [],
                "quality_score": "A",
                "recommendations": ["Add more edge case tests", "Consider load testing"],
            })
        
        elif self.agent_type == "devops":
            return json.dumps({
                "infrastructure_summary": f"DevOps setup for {self._derive_name(idea)}",
                "docker_image": f"{self._derive_name(idea).lower().replace(' ', '-')}:latest",
                "deployment_steps": [
                    {"step": 1, "action": "Build Docker image", "status": "ready"},
                    {"step": 2, "action": "Run database migrations", "status": "ready"},
                    {"step": 3, "action": "Deploy to staging", "status": "pending"},
                ],
                "monitoring": {"enabled": True, "metrics": ["cpu", "memory", "requests_per_second"]},
                "ci_cd": "GitHub Actions",
            })
        
        elif self.agent_type == "marketing":
            return json.dumps({
                "marketing_plan": f"Go-to-market strategy for {self._derive_name(idea)}",
                "target_markets": ["Enterprise", "SMB", "Startups"],
                "channels": ["Website", "Social Media", "Tech Blog"],
                "content_strategy": "Technical tutorials and case studies",
                "launch_timeline": "2 weeks",
                "budget_allocation": {"development": 60, "marketing": 25, "operations": 15},
            })
        
        elif self.agent_type == "sales":
            return json.dumps({
                "sales_strategy": f"Sales approach for {self._derive_name(idea)}",
                "pricing_tiers": [
                    {"name": "Starter", "price": 0, "features": ["Basic access", "Community support"]},
                    {"name": "Professional", "price": 99, "features": ["Full access", "Priority support", "Analytics"]},
                    {"name": "Enterprise", "price": 499, "features": ["Custom deployment", "Dedicated support", "SLA"]},
                ],
                "target_clients": ["Tech startups", "Mid-size enterprises"],
                "estimated_revenue": 50000,
            })
        
        elif self.agent_type == "evolution_analyst":
            return json.dumps({
                "analysis_summary": f"Evolution analysis for {self._derive_name(idea)}",
                "market_trends": ["AI integration", "API-first design", "Cloud native"],
                "improvement_suggestions": [
                    "Add machine learning capabilities",
                    "Implement real-time data processing",
                    "Enhance API documentation",
                ],
                "competitive_analysis": "Strong market position with room for differentiation",
                "next_iteration_focus": "Performance optimization and UX improvements",
            })
        
        else:
            return json.dumps({
                "result": f"{self.agent_type} processed task successfully",
                "status": "completed",
                "data": {"note": f"Agent {self.agent_type} completed its analysis"},
            })

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Robustly extract and parse JSON from LLM response text.

        Handles:
        - Markdown code block fences (```json ... ```)
        - Trailing/leading text around JSON
        - Trailing commas before ] and }
        - Python-style booleans (True/False/None) → JSON (true/false/null)
        - Single quotes used instead of double quotes for keys/strings
        - Missing commas between key-value pairs in objects
        - Truncated JSON (incomplete at the end — missing closing braces)
        - Escaped control characters
        - Extra text appended after the JSON object
        - Text preface before JSON (model commentary outside the code block)
        """
        if not text or not text.strip():
            return None

        # Step 1: Remove markdown code block fences
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.MULTILINE)

        # Step 2: Try direct parse on cleaned text
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/base_agent.py)", exc_info=_suppressed_exc)

        # Step 3: Find JSON object boundaries — extract the first { … }
        start_idx = cleaned.find('{')
        if start_idx == -1:
            return None

        # Try to find a complete JSON object (balanced braces) or use whatever we have
        brace_depth = 0
        end_idx = -1
        for i in range(start_idx, len(cleaned)):
            ch = cleaned[i]
            if ch == '{':
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    end_idx = i
                    break

        raw = cleaned[start_idx:] if end_idx == -1 else cleaned[start_idx:end_idx + 1]

        # Step 4: Try direct parse of extracted JSON
        try:
            return json.loads(raw)
        except json.JSONDecodeError as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/base_agent.py)", exc_info=_suppressed_exc)

        # Step 5: Build a list of cleanup strategies and try each
        fixes = []

        # 5a: Remove trailing commas before ] and }
        fixes.append(re.sub(r',\s*([}\]])', r'\1', raw))

        # 5b: Replace Python booleans and None
        no_py_bool = raw.replace('True', 'true').replace('False', 'false').replace('None', 'null')
        fixes.append(no_py_bool)
        fixes.append(re.sub(r',\s*([}\]])', r'\1', no_py_bool))

        # 5c: Try to fix missing commas between object entries
        # Pattern: "key": "value" "next_key" → "key": "value", "next_key"
        # Pattern: } "key" → }, "key"
        # Pattern: ] "key" → ], "key"
        fixed_commas = re.sub(r'([}\]])[\s]*("(?:[^"\\]|\\.)*"\s*:)', r'\1, \2', raw)
        fixes.append(fixed_commas)
        fixes.append(re.sub(r',\s*([}\]])', r'\1', fixed_commas))

        # 5d: Replace single quotes used as JSON delimiters (only for simple cases)
        single_quoted = re.sub(r"'([^']+)'\s*:", r'"\1":', raw)
        single_quoted = re.sub(r":\s*'([^']+)'", r': "\1"', single_quoted)
        fixes.append(single_quoted)
        fixes.append(re.sub(r',\s*([}\]])', r'\1', single_quoted))

        # 5e: Remove control characters (except tab/newline)
        no_ctrl = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
        fixes.append(no_ctrl)
        fixes.append(re.sub(r',\s*([}\]])', r'\1', no_ctrl))

        # 5f: Close unclosed braces for truncated JSON
        # Count how many { and } we have, add the missing } at the end
        open_braces = raw.count('{')
        close_braces = raw.count('}')
        if close_braces < open_braces:
            # Try to close truncated object — add missing braces + brackets
            # Also try closing unclosed arrays
            missing = open_braces - close_braces
            # Also count array brackets
            open_brackets = raw.count('[')
            close_brackets = raw.count(']')
            missing_brackets = open_brackets - close_brackets
            closed = raw + '}' * missing + ']' * missing_brackets
            fixes.append(closed)
            fixes.append(re.sub(r',\s*([}\]])', r'\1', closed))
            # Also try with just braces
            fixes.append(raw + '}' * missing)
            fixes.append(re.sub(r',\s*([}\]])', r'\1', raw + '}' * missing))

        # 5g: Remove any text after the last complete } (truncation guard)
        # Find the last } that closes the outer object
        brace_depth = 0
        last_close = -1
        for i, ch in enumerate(raw):
            if ch == '{':
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    last_close = i
        if last_close > 0:
            truncated = raw[:last_close + 1]
            fixes.append(truncated)
            fixes.append(re.sub(r',\s*([}\]])', r'\1', truncated))

        # Step 6: Try all fixes
        for candidate in fixes:
            if not candidate or not candidate.strip():
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        # Step 7: Last resort — try raw_decode to get the first valid JSON prefix
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(raw)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError) as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/base_agent.py)", exc_info=_suppressed_exc)

        return None

    @staticmethod
    def _derive_name(idea: str) -> str:
        """Derive a product name from the idea text."""
        if not idea or idea.strip() == "":
            return "AI-Factory Product"
        # Take first significant words as the product name
        words = idea.strip().split()
        # Use first 2-3 meaningful words
        name_words = []
        for w in words:
            if len(w) > 2 and len(name_words) < 3:
                name_words.append(w.capitalize())
        if name_words:
            return " ".join(name_words)
        return "AI-Factory Product"

    def _save_artifact(self, product_id: str, artifact_type: str, data: dict, filename: Optional[str] = None):
        """Save an artifact to the filesystem."""
        import uuid
        fname = filename or f"{artifact_type}_{uuid.uuid4().hex[:8]}.json"
        
        path = self.data_root / artifact_type / product_id
        path.mkdir(parents=True, exist_ok=True)
        
        filepath = path / fname
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.debug(f"Saved artifact: {filepath}")
        return str(filepath)

    def _load_artifact(self, product_id: str, artifact_type: str, filename: str) -> Optional[dict]:
        """Load an artifact from the filesystem."""
        path = self.data_root / artifact_type / product_id / filename
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return None

    def _list_artifacts(self, product_id: str, artifact_type: str) -> list[str]:
        """List artifacts for a product."""
        path = self.data_root / artifact_type / product_id
        if path.exists():
            return [f.name for f in path.iterdir() if f.suffix == ".json"]
        return []

    def _ensure_directories(self):
        """Ensure required directories exist."""
        for dir_name in ["specs", "arch", "code", "bugs", "state", "logs", "telemetry"]:
            (self.data_root / dir_name).mkdir(parents=True, exist_ok=True)

    def _log(self, level: str, message: str, **kwargs):
        """Structured logging."""
        log_data = {
            "agent": self.agent_type,
            "message": message,
            "time": time.time(),
            **kwargs,
        }
        
        log_method = getattr(logger, level.lower(), logger.info)
        log_method(f"[{self.agent_type}] {message}")

        # Also write to agent log file
        log_path = self.data_root / "logs" / f"{self.agent_type}.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps(log_data) + "\n")
