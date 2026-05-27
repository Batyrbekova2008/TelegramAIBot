"""
LLM-as-a-Judge: automatic quality evaluation (Task 27)

Runs a set of reference questions through the bot's LLM, then uses a more
powerful judge model to score each answer on:
  - accuracy (0-10)
  - relevance (0-10)
  - hallucination_free (0-10, higher = less hallucination)

CI gate: mean score >= MIN_PASSING_SCORE (default 7.0)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from groq import AsyncGroq

log = logging.getLogger("llm_judge")

MIN_PASSING_SCORE = 7.0
JUDGE_MODEL = "llama-3.3-70b-versatile"
TESTED_MODEL = "llama-3.1-8b-instant"

REFERENCE_QA: list[dict] = [
    {"question": "Что такое Python?",
     "reference": "Python — высокоуровневый язык программирования общего назначения с динамической типизацией."},
    {"question": "Что такое HTTP?",
     "reference": "HTTP — протокол передачи данных в Интернете между клиентом и сервером."},
    {"question": "Что такое база данных?",
     "reference": "База данных — организованная совокупность структурированных данных."},
    {"question": "Что такое алгоритм?",
     "reference": "Алгоритм — конечная последовательность инструкций для решения задачи."},
    {"question": "Что такое рекурсия?",
     "reference": "Рекурсия — способ определения функции через вызов самой себя."},
]


@dataclass
class EvalResult:
    question: str
    reference: str
    answer: str
    accuracy: float = 0.0
    relevance: float = 0.0
    hallucination_free: float = 0.0
    mean_score: float = 0.0
    judge_reasoning: str = ""
    error: str = ""


@dataclass
class EvalReport:
    results: list[EvalResult] = field(default_factory=list)
    mean_accuracy: float = 0.0
    mean_relevance: float = 0.0
    mean_hallucination_free: float = 0.0
    overall_mean: float = 0.0
    passed: bool = False
    threshold: float = MIN_PASSING_SCORE


_JUDGE_PROMPT = """You are a strict evaluator of AI assistant responses.

Question: {question}
Reference answer: {reference}
Model answer: {answer}

Rate the model answer on these criteria (0-10 each):
1. accuracy: Is the answer factually correct compared to the reference?
2. relevance: Does the answer address what was asked?
3. hallucination_free: Does the answer avoid making up facts not in the reference? (10 = no hallucinations)

Respond ONLY with valid JSON like:
{{"accuracy": 8, "relevance": 9, "hallucination_free": 10, "reasoning": "brief explanation"}}"""


class LLMJudge:
    def __init__(self, groq_client: "AsyncGroq"):
        self.groq = groq_client

    async def _get_answer(self, question: str) -> str:
        try:
            resp = await self.groq.chat.completions.create(
                model=TESTED_MODEL,
                messages=[
                    {"role": "system", "content": "Ты вежливый помощник студента. Отвечай кратко."},
                    {"role": "user", "content": question},
                ],
                timeout=10,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"ERROR: {e}"

    async def _judge_answer(self, question: str, reference: str, answer: str) -> dict:
        if answer.startswith("ERROR:"):
            return {"accuracy": 0, "relevance": 0, "hallucination_free": 0, "reasoning": answer}
        try:
            prompt = _JUDGE_PROMPT.format(
                question=question, reference=reference, answer=answer
            )
            resp = await self.groq.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                timeout=15,
                temperature=0,
            )
            raw = resp.choices[0].message.content or "{}"
            # Strip markdown code blocks if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning("Judge JSON parse error: %s", e)
            return {"accuracy": 5, "relevance": 5, "hallucination_free": 5,
                    "reasoning": f"parse error: {e}"}
        except Exception as e:
            log.error("Judge error: %s", e)
            return {"accuracy": 0, "relevance": 0, "hallucination_free": 0, "reasoning": str(e)}

    async def evaluate(
        self,
        qa_pairs: list[dict] | None = None,
        progress_callback=None,
    ) -> EvalReport:
        qa_pairs = qa_pairs or REFERENCE_QA
        results = []

        for i, qa in enumerate(qa_pairs, 1):
            question = qa["question"]
            reference = qa.get("reference", "")

            if progress_callback:
                await progress_callback(i, len(qa_pairs), question)

            answer = await self._get_answer(question)
            scores = await self._judge_answer(question, reference, answer)

            acc = float(scores.get("accuracy", 0))
            rel = float(scores.get("relevance", 0))
            hal = float(scores.get("hallucination_free", 0))
            mean = (acc + rel + hal) / 3

            results.append(EvalResult(
                question=question,
                reference=reference,
                answer=answer,
                accuracy=acc,
                relevance=rel,
                hallucination_free=hal,
                mean_score=mean,
                judge_reasoning=scores.get("reasoning", ""),
            ))

        if results:
            mean_acc = sum(r.accuracy for r in results) / len(results)
            mean_rel = sum(r.relevance for r in results) / len(results)
            mean_hal = sum(r.hallucination_free for r in results) / len(results)
            overall = (mean_acc + mean_rel + mean_hal) / 3
        else:
            mean_acc = mean_rel = mean_hal = overall = 0.0

        report = EvalReport(
            results=results,
            mean_accuracy=round(mean_acc, 2),
            mean_relevance=round(mean_rel, 2),
            mean_hallucination_free=round(mean_hal, 2),
            overall_mean=round(overall, 2),
            passed=overall >= MIN_PASSING_SCORE,
            threshold=MIN_PASSING_SCORE,
        )
        if not report.passed:
            log.warning(
                "LLM quality gate FAILED: overall=%.2f < threshold=%.2f",
                overall, MIN_PASSING_SCORE,
            )
        return report

    def format_report(self, report: EvalReport) -> str:
        lines = [
            f"📊 <b>LLM Quality Report</b>",
            f"Threshold: {report.threshold}/10",
            f"{'✅ PASSED' if report.passed else '❌ FAILED'}",
            f"",
            f"Mean accuracy:      {report.mean_accuracy:.1f}/10",
            f"Mean relevance:     {report.mean_relevance:.1f}/10",
            f"Mean halluc-free:   {report.mean_hallucination_free:.1f}/10",
            f"Overall mean:       {report.overall_mean:.1f}/10",
            f"",
            f"<b>Per-question results:</b>",
        ]
        for r in report.results:
            lines.append(
                f"• {r.question[:40]}: "
                f"acc={r.accuracy:.0f} rel={r.relevance:.0f} hal={r.hallucination_free:.0f} "
                f"→ {r.mean_score:.1f}/10"
            )
        return "\n".join(lines)
