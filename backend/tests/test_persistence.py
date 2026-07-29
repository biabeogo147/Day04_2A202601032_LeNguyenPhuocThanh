from app.agent.shared.persistence import Database
from app.schemas import ProfileCreate


async def test_profile_session_run_and_trace_are_persisted(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    await database.create_schema()

    profile = await database.create_profile(
        ProfileCreate(
            display_name="Mentor persona",
            age_group="adult",
            goals=["tim mạch"],
            conditions=[],
            medications=[],
            allergies=["cá"],
            pregnancy_status="not_applicable",
            budget_max_vnd=500_000,
            preferred_dosage_forms=["Viên nang mềm"],
        )
    )
    session = await database.create_session(
        profile_id=profile.id,
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

    assert profile.id
    assert session.profile_id == profile.id
    assert run.status == "queued"
    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.type for event in await database.list_trace(run.id, after_sequence=0)] == [
        "run.started",
        "tool.started",
    ]
    assert [event.sequence for event in await database.list_trace(run.id, after_sequence=1)] == [2]

    await database.close()


async def test_profile_patch_and_delete_are_explicit(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    await database.create_schema()
    profile = await database.create_profile(
        ProfileCreate(
            display_name="A",
            age_group="adult",
            goals=["ngủ ngon"],
            budget_max_vnd=200_000,
            preferred_dosage_forms=["Viên nén"],
        )
    )

    updated = await database.update_profile(profile.id, {"budget_max_vnd": 350_000})

    assert updated.budget_max_vnd == 350_000
    assert await database.delete_profile(profile.id) is True
    assert await database.get_profile(profile.id) is None
    await database.close()
