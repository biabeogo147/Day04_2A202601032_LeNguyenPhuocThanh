from app.agent.shared.persistence import Database


async def test_session_run_and_trace_are_persisted(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    await database.create_schema()

    session = await database.create_session(
        context={"age_group": "adult", "goals": ["tim mạch"], "allergies": ["cá"]},
        version_id="version_1",
        provider="openai",
        chat_model="gpt-4o-mini",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        dataset_fingerprint="abc123",
    )
    run = await database.create_run(session.id, "Tư vấn Omega-3")
    first = await database.append_trace(run.id, "run.started", {"message": "started"})
    second = await database.append_trace(run.id, "tool.started", {"tool": "search"})

    assert session.context["age_group"] == "adult"
    assert run.status == "queued"
    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.type for event in await database.list_trace(run.id, after_sequence=0)] == [
        "run.started",
        "tool.started",
    ]
    assert [event.sequence for event in await database.list_trace(run.id, after_sequence=1)] == [2]

    await database.close()


async def test_session_context_merges_known_fields(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'context.db'}")
    await database.create_schema()

    session = await database.create_session(
        version_id="version_1",
        provider="openai",
        chat_model="gpt-4o-mini",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        dataset_fingerprint="abc123",
    )

    assert session.context == {}

    updated = await database.update_session_context(
        session.id,
        {"age_group": "adult", "conditions": []},
    )
    updated = await database.update_session_context(
        session.id,
        {"goals": ["tim mạch"]},
    )

    assert updated.context == {
        "age_group": "adult",
        "conditions": [],
        "goals": ["tim mạch"],
    }
    await database.close()
