#!/usr/bin/env python3
"""
Sample Questions CLI

A tool for viewing sample questions and answers from tenant databases with clean formatting.
"""

import asyncio
import json
import os
from typing import Any

import asyncpg
import typer
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

# Load environment variables
load_dotenv()

app = typer.Typer(
    name="questions",
    help="Sample questions and answers management for Corporate Context",
    add_completion=False,
)
console = Console()


def log_info(message: str) -> None:
    """Log info message with emoji."""
    console.print(f"ℹ️  {message}", style="blue")


def log_success(message: str) -> None:
    """Log success message with emoji."""
    console.print(f"✅ {message}", style="green")


def log_warning(message: str) -> None:
    """Log warning message with emoji."""
    console.print(f"⚠️  {message}", style="yellow")


def log_error(message: str) -> None:
    """Log error message with emoji."""
    console.print(f"❌ {message}", style="red")


def validate_environment() -> tuple[str | None, str | None, str | None, str | None]:
    """Validate required environment variables and return tenant database connection info."""
    # Tenant database credentials
    tenant_host = os.getenv("PG_TENANT_DATABASE_HOST")
    tenant_port = os.getenv("PG_TENANT_DATABASE_PORT", "5432")
    tenant_username = os.getenv("PG_TENANT_DATABASE_ADMIN_USERNAME")
    tenant_password = os.getenv("PG_TENANT_DATABASE_ADMIN_PASSWORD")

    return tenant_host, tenant_port, tenant_username, tenant_password


def get_tenant_db_url(tenant_id: str, host: str, port: str, username: str, password: str) -> str:
    """Construct tenant database URL."""
    return f"postgresql://{username}:{password}@{host}:{port}/db_{tenant_id}"


async def test_database_connectivity(db_url: str, timeout: int = 10) -> bool:
    """Test if we can connect to a database."""
    try:
        conn = await asyncio.wait_for(asyncpg.connect(db_url), timeout=timeout)
        await conn.execute("SELECT 1")
        await conn.close()
        return True
    except Exception:
        return False


def format_metadata(metadata: dict[str, Any] | str | None) -> str:
    """Format metadata JSON for display."""
    if not metadata:
        return ""

    # Parse JSON string if needed
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return ""

    if not isinstance(metadata, dict):
        return ""

    # Extract key information from metadata
    parts = []
    if "channel_name" in metadata:
        parts.append(f"#{metadata['channel_name']}")
    if "username" in metadata:
        parts.append(f"@{metadata['username']}")
    if "thread_reply_count" in metadata and metadata["thread_reply_count"] > 0:
        parts.append(f"{metadata['thread_reply_count']} replies")
    if "reaction_count" in metadata and metadata["reaction_count"] > 0:
        parts.append(f"{metadata['reaction_count']} reactions")

    return " • ".join(parts)


def format_confidence(confidence: float | None) -> str:
    """Format confidence score with color coding."""
    if confidence is None:
        return ""

    percentage = confidence * 100
    if confidence >= 0.8:
        return f"[green]{percentage:.1f}%[/green]"
    elif confidence >= 0.6:
        return f"[yellow]{percentage:.1f}%[/yellow]"
    else:
        return f"[red]{percentage:.1f}%[/red]"


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def display_question_card(row: dict, index: int, show_answer: bool = False) -> None:
    """Display a single question as a card with full text."""
    console.print(f"[bold cyan]Question #{index}[/bold cyan]")
    console.print()

    # Display full question text
    console.print(f"[bold]Q:[/bold] {escape(row['question_text'])}")
    console.print()

    # Display answer if present and requested
    if show_answer and "answer_text" in row and row["answer_text"]:
        confidence_text = format_confidence(row.get("confidence_score"))
        console.print(f"[bold]A:[/bold] ({confidence_text})")
        console.print(escape(row["answer_text"]))
        console.print()

    # Display metadata in a readable format
    details = []
    if row["score"]:
        details.append(f"Score: [yellow]{row['score']:.2f}[/yellow]")
    if row["source"]:
        details.append(f"Source: [blue]{row['source']}[/blue]")

    # Format context from metadata
    context = format_metadata(row["metadata"])
    if context:
        details.append(f"Context: [dim]{context}[/dim]")

    # Add source documents for answered questions
    if show_answer and "source_documents" in row:
        sources = format_source_documents(row["source_documents"])
        if sources:
            details.append(f"Sources: [dim]{sources}[/dim]")

    if row["created_at"]:
        details.append(f"Created: [dim]{row['created_at'].strftime('%Y-%m-%d %H:%M')}[/dim]")

    if show_answer and "generated_at" in row and row["generated_at"]:
        details.append(f"Answered: [dim]{row['generated_at'].strftime('%Y-%m-%d %H:%M')}[/dim]")

    if details:
        console.print(" • ".join(details))
        console.print()

    console.print("─" * 80)
    console.print()


def format_source_documents(source_docs: list[dict[str, Any]] | str | None) -> str:
    """Format source documents for display."""
    if not source_docs:
        return ""

    # Parse JSON string if needed
    if isinstance(source_docs, str):
        try:
            source_docs = json.loads(source_docs)
        except json.JSONDecodeError:
            return ""

    if not isinstance(source_docs, list):
        return ""

    doc_summaries = []
    for doc in source_docs[:3]:  # Show up to 3 sources
        if not isinstance(doc, dict):
            continue  # type: ignore[unreachable]
        if "title" in doc:
            doc_summaries.append(doc["title"])
        elif "file_name" in doc:
            doc_summaries.append(doc["file_name"])
        elif "source" in doc:
            doc_summaries.append(doc["source"])

    result = ", ".join(doc_summaries)
    if len(source_docs) > 3:
        result += f" (+{len(source_docs) - 3} more)"

    return result


@app.command()
def unanswered(
    tenant_id: str = typer.Argument(..., help="Tenant ID to query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of questions to show"),
    source: str | None = typer.Option(None, "--source", help="Filter by source (e.g., 'slack')"),
    min_score: float | None = typer.Option(None, "--min-score", help="Minimum score threshold"),
) -> None:
    """Show top N unanswered questions for a tenant."""

    asyncio.run(show_unanswered_questions(tenant_id, limit, source, min_score))


@app.command()
def answered(
    tenant_id: str = typer.Argument(..., help="Tenant ID to query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of questions to show"),
    source: str | None = typer.Option(None, "--source", help="Filter by source (e.g., 'slack')"),
    min_confidence: float | None = typer.Option(
        None, "--min-confidence", help="Minimum confidence threshold (0.0-1.0)"
    ),
    show_answers: bool = typer.Option(
        True, "--show-answers/--no-answers", help="Show full answer text"
    ),
) -> None:
    """Show top N answered questions with answers for a tenant."""

    asyncio.run(show_answered_questions(tenant_id, limit, source, min_confidence, show_answers))


async def show_unanswered_questions(
    tenant_id: str, limit: int, source: str | None, min_score: float | None
) -> None:
    """Show unanswered questions for a tenant."""

    console.print(f"[blue]📋 Unanswered Questions for Tenant: {tenant_id}[/blue]")
    console.print("=" * 60)
    console.print()

    # Validate environment
    tenant_host, tenant_port, tenant_username, tenant_password = validate_environment()

    if not all([tenant_host, tenant_username, tenant_password]):
        log_error("Tenant database credentials not configured")
        log_error(
            "Set PG_TENANT_DATABASE_HOST, PG_TENANT_DATABASE_ADMIN_USERNAME, and PG_TENANT_DATABASE_ADMIN_PASSWORD"
        )
        raise typer.Exit(1)

    # Connect to tenant database
    assert tenant_host is not None
    assert tenant_port is not None
    assert tenant_username is not None
    assert tenant_password is not None
    tenant_db_url = get_tenant_db_url(
        tenant_id, tenant_host, tenant_port, tenant_username, tenant_password
    )

    if not await test_database_connectivity(tenant_db_url):
        log_error(f"Cannot connect to tenant database for {tenant_id}")
        raise typer.Exit(1)

    try:
        conn = await asyncpg.connect(tenant_db_url)
        try:
            # Build query
            where_conditions = ["sa.question_id IS NULL"]  # No answer exists
            params: list[Any] = []
            param_count = 0

            if source:
                param_count += 1
                where_conditions.append(f"sq.source = ${param_count}")
                params.append(source)

            if min_score is not None:
                param_count += 1
                where_conditions.append(f"sq.score >= ${param_count}")
                params.append(min_score)

            param_count += 1
            params.append(limit)

            query = f"""
                SELECT
                    sq.id,
                    sq.question_text,
                    sq.source,
                    sq.source_id,
                    sq.metadata,
                    sq.score,
                    sq.created_at
                FROM sample_questions sq
                LEFT JOIN sample_answers sa ON sq.id = sa.question_id
                WHERE {" AND ".join(where_conditions)}
                ORDER BY sq.score DESC, sq.created_at DESC
                LIMIT ${param_count}
            """

            rows = await conn.fetch(query, *params)

            if not rows:
                log_info("No unanswered questions found matching criteria")
                return

            # Display questions as cards instead of table
            for i, row in enumerate(rows, 1):
                display_question_card(row, i)
            console.print()
            log_success(f"Found {len(rows)} unanswered questions")

            if len(rows) == limit:
                log_info(f"Showing top {limit} results. Use --limit to see more.")

        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Error querying unanswered questions: {e}")
        raise typer.Exit(1)


async def show_answered_questions(
    tenant_id: str, limit: int, source: str | None, min_confidence: float | None, show_answers: bool
) -> None:
    """Show answered questions for a tenant."""

    console.print(f"[blue]📋 Answered Questions for Tenant: {tenant_id}[/blue]")
    console.print("=" * 60)
    console.print()

    # Validate environment
    tenant_host, tenant_port, tenant_username, tenant_password = validate_environment()

    if not all([tenant_host, tenant_username, tenant_password]):
        log_error("Tenant database credentials not configured")
        log_error(
            "Set PG_TENANT_DATABASE_HOST, PG_TENANT_DATABASE_ADMIN_USERNAME, and PG_TENANT_DATABASE_ADMIN_PASSWORD"
        )
        raise typer.Exit(1)

    # Connect to tenant database
    assert tenant_host is not None
    assert tenant_port is not None
    assert tenant_username is not None
    assert tenant_password is not None
    tenant_db_url = get_tenant_db_url(
        tenant_id, tenant_host, tenant_port, tenant_username, tenant_password
    )

    if not await test_database_connectivity(tenant_db_url):
        log_error(f"Cannot connect to tenant database for {tenant_id}")
        raise typer.Exit(1)

    try:
        conn = await asyncpg.connect(tenant_db_url)
        try:
            # Build query
            where_conditions = ["sa.question_id IS NOT NULL"]  # Answer exists
            params: list[Any] = []
            param_count = 0

            if source:
                param_count += 1
                where_conditions.append(f"sq.source = ${param_count}")
                params.append(source)

            if min_confidence is not None:
                param_count += 1
                where_conditions.append(f"sa.confidence_score >= ${param_count}")
                params.append(min_confidence)

            param_count += 1
            params.append(limit)

            query = f"""
                SELECT
                    sq.id,
                    sq.question_text,
                    sq.source,
                    sq.source_id,
                    sq.metadata,
                    sq.score,
                    sq.created_at,
                    sa.answer_text,
                    sa.confidence_score,
                    sa.source_documents,
                    sa.generated_at
                FROM sample_questions sq
                JOIN sample_answers sa ON sq.id = sa.question_id
                WHERE {" AND ".join(where_conditions)}
                ORDER BY sa.confidence_score DESC, sq.score DESC, sq.created_at DESC
                LIMIT ${param_count}
            """

            rows = await conn.fetch(query, *params)

            if not rows:
                log_info("No answered questions found matching criteria")
                return

            if show_answers:
                # Show detailed view with answers using cards
                for i, row in enumerate(rows, 1):
                    display_question_card(row, i, show_answer=True)
            else:
                # Show card view without full answers
                for i, row in enumerate(rows, 1):
                    display_question_card(row, i, show_answer=False)
                log_info("Use --show-answers to see full answer text")

            log_success(f"Found {len(rows)} answered questions")

            if len(rows) == limit:
                log_info(f"Showing top {limit} results. Use --limit to see more.")

        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Error querying answered questions: {e}")
        raise typer.Exit(1)


@app.command()
def stats(
    tenant_id: str = typer.Argument(..., help="Tenant ID to query"),
) -> None:
    """Show statistics about sample questions and answers for a tenant."""

    asyncio.run(show_stats(tenant_id))


async def show_stats(tenant_id: str) -> None:
    """Show statistics about questions and answers."""

    console.print(f"[blue]📊 Sample Questions Statistics for Tenant: {tenant_id}[/blue]")
    console.print("=" * 60)
    console.print()

    # Validate environment
    tenant_host, tenant_port, tenant_username, tenant_password = validate_environment()

    if not all([tenant_host, tenant_username, tenant_password]):
        log_error("Tenant database credentials not configured")
        raise typer.Exit(1)

    # Connect to tenant database
    assert tenant_host is not None
    assert tenant_port is not None
    assert tenant_username is not None
    assert tenant_password is not None
    tenant_db_url = get_tenant_db_url(
        tenant_id, tenant_host, tenant_port, tenant_username, tenant_password
    )

    if not await test_database_connectivity(tenant_db_url):
        log_error(f"Cannot connect to tenant database for {tenant_id}")
        raise typer.Exit(1)

    try:
        conn = await asyncpg.connect(tenant_db_url)
        try:
            # Get basic counts
            stats_query = """
                SELECT
                    COUNT(*) as total_questions,
                    COUNT(DISTINCT source) as unique_sources,
                    COALESCE(AVG(score), 0) as avg_score,
                    COALESCE(MAX(score), 0) as max_score,
                    COALESCE(MIN(score), 0) as min_score
                FROM sample_questions
            """
            stats = await conn.fetchrow(stats_query)

            # Get answered questions count
            answered_query = """
                SELECT COUNT(DISTINCT sq.id) as answered_questions
                FROM sample_questions sq
                JOIN sample_answers sa ON sq.id = sa.question_id
            """
            answered = await conn.fetchrow(answered_query)

            # Get source breakdown
            sources_query = """
                SELECT
                    source,
                    COUNT(*) as question_count,
                    COUNT(sa.id) as answered_count
                FROM sample_questions sq
                LEFT JOIN sample_answers sa ON sq.id = sa.question_id
                GROUP BY source
                ORDER BY question_count DESC
            """
            sources = await conn.fetch(sources_query)

            # Get confidence breakdown for answers
            confidence_query = """
                SELECT
                    CASE
                        WHEN confidence_score >= 0.8 THEN 'High (≥80%)'
                        WHEN confidence_score >= 0.6 THEN 'Medium (60-79%)'
                        WHEN confidence_score >= 0.4 THEN 'Low (40-59%)'
                        ELSE 'Very Low (<40%)'
                    END as confidence_range,
                    COUNT(*) as answer_count,
                    COALESCE(AVG(confidence_score), 0) as avg_confidence
                FROM sample_answers
                GROUP BY
                    CASE
                        WHEN confidence_score >= 0.8 THEN 'High (≥80%)'
                        WHEN confidence_score >= 0.6 THEN 'Medium (60-79%)'
                        WHEN confidence_score >= 0.4 THEN 'Low (40-59%)'
                        ELSE 'Very Low (<40%)'
                    END
                ORDER BY avg_confidence DESC
            """
            confidence_breakdown = await conn.fetch(confidence_query)

            # Display overall stats
            console.print("[bold]Overall Statistics[/bold]")
            console.print(f"Total Questions: {stats['total_questions']}")
            console.print(f"Answered Questions: {answered['answered_questions']}")
            unanswered = stats["total_questions"] - answered["answered_questions"]
            console.print(f"Unanswered Questions: {unanswered}")

            if stats["total_questions"] > 0:
                answer_rate = (answered["answered_questions"] / stats["total_questions"]) * 100
                console.print(f"Answer Rate: {answer_rate:.1f}%")

            console.print(f"Unique Sources: {stats['unique_sources']}")
            console.print(f"Average Score: {stats['avg_score']:.2f}")
            console.print(f"Score Range: {stats['min_score']:.2f} - {stats['max_score']:.2f}")
            console.print()

            # Display source breakdown
            if sources:
                console.print("[bold]Questions by Source[/bold]")
                source_table = Table(box=box.ROUNDED)
                source_table.add_column("Source", style="bold")
                source_table.add_column("Questions", justify="right")
                source_table.add_column("Answered", justify="right")
                source_table.add_column("Answer Rate", justify="right")

                for row in sources:
                    source_name = row["source"] or "Unknown"
                    questions = row["question_count"]
                    answered_count = row["answered_count"]
                    rate = (answered_count / questions) * 100 if questions > 0 else 0

                    source_table.add_row(
                        source_name, str(questions), str(answered_count), f"{rate:.1f}%"
                    )

                console.print(source_table)
                console.print()

            # Display confidence breakdown
            if confidence_breakdown:
                console.print("[bold]Answer Quality Distribution[/bold]")
                conf_table = Table(box=box.ROUNDED)
                conf_table.add_column("Confidence Level", style="bold")
                conf_table.add_column("Count", justify="right")
                conf_table.add_column("Avg. Confidence", justify="right")

                for row in confidence_breakdown:
                    conf_table.add_row(
                        row["confidence_range"],
                        str(row["answer_count"]),
                        f"{row['avg_confidence']:.1f}%",
                    )

                console.print(conf_table)

        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Error querying statistics: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
