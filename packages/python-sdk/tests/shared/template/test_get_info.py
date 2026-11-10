from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from e2b import AsyncTemplate, Template, TemplateBuildStatus
from e2b.api.client.api.templates import (
    get_templates_aliases_alias,
    get_templates_template_id,
)
from e2b.api.client.models import TemplateAliasResponse, TemplateWithBuilds
from e2b.api.client.types import UNSET
from e2b.exceptions import InvalidArgumentException, TemplateNotFoundException

BUILD_ID = "22222222-2222-2222-2222-222222222222"
FIXED_BUILD_ID = "11111111-1111-1111-1111-111111111111"


def _build(build_id, **extra):
    return {
        "buildID": build_id,
        "status": "ready",
        "cpuCount": 2,
        "memoryMB": 1024,
        "createdAt": "2026-11-05T15:00:00Z",
        "updatedAt": "2026-11-05T15:01:00Z",
        **extra,
    }


def _alias_response(status_code=200):
    return SimpleNamespace(
        status_code=status_code,
        content=b'{"code": 404, "message": "Template not found"}',
        headers={},
        parsed=(
            TemplateAliasResponse(template_id="template-id", public=False)
            if status_code == 200
            else None
        ),
    )


def _template_response(**extra):
    return SimpleNamespace(
        status_code=200,
        parsed=TemplateWithBuilds.from_dict(
            {
                "templateID": "template-id",
                "buildID": BUILD_ID,
                "cpuCount": 2,
                "maxCpuCount": 4,
                "memoryMB": 1024,
                "diskSizeMB": 5120,
                "public": False,
                "aliases": ["resizable"],
                "names": ["team/resizable"],
                "createdAt": "2026-11-05T14:00:00Z",
                "updatedAt": "2026-11-05T15:01:00Z",
                "createdBy": None,
                "lastSpawnedAt": None,
                "spawnCount": 0,
                "buildCount": 2,
                "envdVersion": "0.2.4",
                "buildStatus": "ready",
                "builds": [
                    _build(
                        BUILD_ID,
                        maxCpuCount=4,
                        diskSizeMB=5120,
                        finishedAt="2026-11-05T15:01:00Z",
                    ),
                    _build(FIXED_BUILD_ID),
                ],
                **extra,
            }
        ),
    )


def _assert_info(info, template_request):
    assert template_request.call_args.kwargs["template_id"] == "template-id"
    assert info.template_id == "template-id"
    assert info.names == ["team/resizable"]
    assert (info.cpu_count, info.max_cpu_count) == (2, 4)

    resizable, fixed = info.builds
    assert resizable.build_id == BUILD_ID
    assert resizable.status == TemplateBuildStatus.READY
    assert (resizable.cpu_count, resizable.max_cpu_count) == (2, 4)
    assert resizable.disk_size_mb == 5120
    assert isinstance(resizable.finished_at, datetime)
    assert fixed.max_cpu_count is None
    assert fixed.disk_size_mb is None
    assert fixed.finished_at is None


def test_get_info_resolves_name_and_maps_cpu_counts(monkeypatch, test_api_key):
    alias_request = Mock(return_value=_alias_response())
    template_request = Mock(return_value=_template_response())
    monkeypatch.setattr(get_templates_aliases_alias, "sync_detailed", alias_request)
    monkeypatch.setattr(get_templates_template_id, "sync_detailed", template_request)

    info = Template.get_info("resizable", api_key=test_api_key)

    assert alias_request.call_args.kwargs["alias"] == "resizable"
    _assert_info(info, template_request)


async def test_async_get_info_resolves_name_and_maps_cpu_counts(
    monkeypatch, test_api_key
):
    alias_request = AsyncMock(return_value=_alias_response())
    template_request = AsyncMock(return_value=_template_response())
    monkeypatch.setattr(get_templates_aliases_alias, "asyncio_detailed", alias_request)
    monkeypatch.setattr(get_templates_template_id, "asyncio_detailed", template_request)

    info = await AsyncTemplate.get_info("resizable", api_key=test_api_key)

    assert alias_request.call_args.kwargs["alias"] == "resizable"
    _assert_info(info, template_request)


@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
async def test_get_info_raises_for_unknown_template(
    monkeypatch, test_api_key, is_async
):
    mock = AsyncMock if is_async else Mock
    method = "asyncio_detailed" if is_async else "sync_detailed"
    monkeypatch.setattr(
        get_templates_aliases_alias,
        method,
        mock(return_value=_alias_response(404)),
    )
    template_request = mock()
    monkeypatch.setattr(get_templates_template_id, method, template_request)

    with pytest.raises(TemplateNotFoundException, match="Template 'missing' not found"):
        if is_async:
            await AsyncTemplate.get_info("missing", api_key=test_api_key)
        else:
            Template.get_info("missing", api_key=test_api_key)

    template_request.assert_not_called()


@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("case", ["tagged", "no_default", "failed_rebuild"])
async def test_get_info_edge_cases(monkeypatch, test_api_key, is_async, case):
    response = _template_response(
        buildStatus="error" if case == "failed_rebuild" else "waiting"
    )
    response.parsed.max_cpu_count = UNSET
    if case == "no_default":
        response.parsed.build_id = "00000000-0000-0000-0000-000000000000"
        response.parsed.cpu_count = 0
        response.parsed.memory_mb = 0
        response.parsed.disk_size_mb = 0
        response.parsed.envd_version = ""

    mock = AsyncMock if is_async else Mock
    method = "asyncio_detailed" if is_async else "sync_detailed"
    alias_request = mock(return_value=_alias_response())
    template_request = mock(return_value=response)
    monkeypatch.setattr(get_templates_aliases_alias, method, alias_request)
    monkeypatch.setattr(get_templates_template_id, method, template_request)

    async def get_info(name):
        if is_async:
            return await AsyncTemplate.get_info(name, api_key=test_api_key)
        return Template.get_info(name, api_key=test_api_key)

    if case == "tagged":
        with pytest.raises(
            InvalidArgumentException, match=r"Use get_info\('resizable'\)"
        ):
            await get_info("resizable:v1")
        alias_request.assert_not_called()
        template_request.assert_not_called()
        return

    info = await get_info("resizable")
    if case == "no_default":
        assert info.build_id is None
        assert info.cpu_count is None
        assert info.memory_mb is None
        assert info.disk_size_mb is None
        assert info.envd_version is None
        # A ready build under another tag is not the default build.
        assert info.builds[0].cpu_count == 2
    else:
        assert info.build_id == BUILD_ID
        assert info.cpu_count == 2
    assert info.max_cpu_count is None
