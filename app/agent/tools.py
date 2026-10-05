import ast
import inspect
import json
import operator
from datetime import datetime, timezone
from typing import Annotated, get_args, get_origin
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.agent import LongTermMemory
from app.llm import chat_client, chat_model, embedding_client


def web_search(query: str) -> str:
    """Return three mock search snippets for a query."""
    return "\n".join([f"Mock result {i}: Information about {query}." for i in range(1, 4)])


def calculator(expression: str) -> str:
    """Evaluate a safe arithmetic expression."""
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponent too large")
            return ops[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](evaluate(node.operand))
        raise ValueError("Only numeric arithmetic expressions are allowed")
    try:
        return str(evaluate(ast.parse(expression, mode="eval").body))
    except Exception as exc:
        return f"Calculation error: {exc}"


def get_current_datetime() -> str:
    """Return the current UTC date and time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


async def summarise_text(text: str, max_words: int) -> str:
    """Summarise text to approximately max_words words using the configured LLM."""
    if not chat_client:
        return "Summarisation unavailable: configure the selected LLM provider in .env."
    response = await chat_client.chat.completions.create(model=chat_model, messages=[
        {"role": "system", "content": f"Summarize the supplied text in at most {max_words} words."},
        {"role": "user", "content": text}], max_tokens=max(32, min(max_words * 3, 2000)))
    return response.choices[0].message.content or ""


async def remember_fact(fact: str, *, db: AsyncSession, user_id: str, run_id: str) -> str:
    """Embed and save a fact in the user's long-term memory."""
    if not embedding_client:
        return "Long-term memory unavailable: configure OPENAI_API_KEY for embeddings."
    embedding = (await embedding_client.embeddings.create(model="text-embedding-3-small", input=fact)).data[0].embedding
    db.add(LongTermMemory(user_id=user_id, content=fact, embedding=embedding, source_run_id=run_id))
    await db.commit()
    return "Fact saved to long-term memory."


TOOL_FUNCTIONS = {fn.__name__: fn for fn in (web_search, calculator, get_current_datetime, summarise_text, remember_fact)}
_TYPE_SCHEMA = {str: {"type": "string"}, int: {"type": "integer"}, float: {"type": "number"}, bool: {"type": "boolean"}}


def _schema_type(annotation):
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    return _TYPE_SCHEMA.get(annotation, {"type": "string"})


def tool_definition(fn):
    sig = inspect.signature(fn)
    props, required = {}, []
    for name, param in sig.parameters.items():
        if name in {"db", "user_id", "run_id"}:
            continue
        props[name] = _schema_type(param.annotation)
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "function", "function": {"name": fn.__name__, "description": inspect.getdoc(fn) or "", "parameters": {"type": "object", "properties": props, "required": required, "additionalProperties": False}}}


TOOL_DEFINITIONS = {name: tool_definition(fn) for name, fn in TOOL_FUNCTIONS.items()}


async def dispatch_tool(name: str, arguments: str, *, db: AsyncSession, user_id: str, run_id: str) -> str:
    try:
        fn = TOOL_FUNCTIONS[name]
        parsed = json.loads(arguments or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object")
        allowed = set(inspect.signature(fn).parameters) - {"db", "user_id", "run_id"}
        if set(parsed) - allowed:
            raise ValueError("Unexpected tool argument")
        kwargs = {k: v for k, v in parsed.items() if k in allowed}
        if name == "remember_fact":
            kwargs.update(db=db, user_id=user_id, run_id=run_id)
        result = fn(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return str(result)
    except Exception as exc:
        return f"Tool error ({name}): {type(exc).__name__}: {exc}"
