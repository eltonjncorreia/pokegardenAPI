"""Modelo roteirizado para rodar o Runner REAL do Agents SDK sem a OpenAI.

Cada passo do roteiro é uma resposta do "modelo" em um turno: uma ou mais
chamadas de tool (``call``) ou a saída final estruturada (``final``). O SDK
executa as tools de verdade (descoberta, gating do catálogo, validação de
argumentos, orçamento), então o teste cobre a integração com o SDK.

Limitação: é um replay. Prova que o runtime trata corretamente as decisões
roteirizadas (inclusive as maliciosas), não que um modelo real as tomaria.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from agents import Model, ModelResponse, Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText


@dataclass(frozen=True)
class Call:
    """Chamada de uma tool do agente (``search_tools``, ``get_tool_schema``, ``run_tool``)."""

    tool: str
    args: dict


@dataclass(frozen=True)
class Final:
    """Saída final no formato de ``agent.AgentOutput``."""

    status: str
    answer: str


Step = Call | Final | list[Call]


def call(tool: str, **args: object) -> Call:
    """Atalho: ``call("run_tool", name="get_pokemon", args={...})``."""
    return Call(tool, args)


def final(status: str, answer: str) -> Final:
    """Atalho para a resposta final do modelo."""
    return Final(status, answer)


@dataclass
class ScriptedModel(Model):
    """Responde cada turno com o próximo passo do roteiro.

    ``delay_s`` cede o event loop a cada turno (útil para intercalar requisições
    paralelas). Os outputs de tool recebidos ficam em ``observed`` para evidência.
    """

    script: list[Step]
    delay_s: float = 0.0
    observed: list[dict] = field(default_factory=list)
    _turn: int = 0

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **_):  # type: ignore[override]  # noqa: A002, ANN001
        """Devolve o próximo passo do roteiro no formato de saída do Responses API."""
        self._observe(input)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self._turn >= len(self.script):
            raise RuntimeError(f"roteiro esgotado no turno {self._turn + 1}")
        step = self.script[self._turn]
        self._turn += 1
        return ModelResponse(output=self._items(step), usage=Usage(requests=1), response_id=None)

    def stream_response(self, *args, **kwargs) -> AsyncIterator:  # type: ignore[override]  # noqa: ANN002, ANN003
        """Streaming não é usado pelo PokéGarden."""
        raise NotImplementedError("ScriptedModel não suporta streaming")

    def _items(self, step: Step) -> list:
        if isinstance(step, Final):
            text = json.dumps({"status": step.status, "answer": step.answer}, ensure_ascii=False)
            content = [ResponseOutputText(text=text, type="output_text", annotations=[], logprobs=[])]
            return [ResponseOutputMessage(id=f"msg_{self._turn}", content=content, role="assistant", status="completed", type="message")]
        calls = step if isinstance(step, list) else [step]
        return [
            ResponseFunctionToolCall(
                id=f"fc_{self._turn}_{i}",
                call_id=f"call_{self._turn}_{i}",
                name=c.tool,
                arguments=json.dumps(c.args, ensure_ascii=False),
                type="function_call",
            )
            for i, c in enumerate(calls)
        ]

    def _observe(self, input: object) -> None:  # noqa: A002
        """Guarda os outputs de tool que o runtime devolveu ao modelo neste turno."""
        if not isinstance(input, list):
            return
        seen = {o["call_id"] for o in self.observed}
        for item in input:
            item = item if isinstance(item, dict) else getattr(item, "model_dump", lambda: {})()
            if item.get("type") == "function_call_output" and item.get("call_id") not in seen:
                self.observed.append({"call_id": item["call_id"], "output": item.get("output")})
