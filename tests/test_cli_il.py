from types import SimpleNamespace

import pytest

from cli import cmd_il_activate, cmd_il_put


def test_cmd_il_put_dry_run_prints_preview(monkeypatch, capsys):
    league = SimpleNamespace(
        move_player_to_il=lambda team_id, player, execute: {
            'teamId': team_id,
            'scoringPeriodId': 13,
            'items': [{
                'playerId': 42,
                'fromLineupSlotId': 16,
                'toLineupSlotId': 17,
            }],
        }
    )
    team = SimpleNamespace(team_id=5)

    monkeypatch.setattr('cli.get_league', lambda: league)
    monkeypatch.setattr('cli.get_my_team', lambda _league: team)

    cmd_il_put(SimpleNamespace(player='Nick Lodolo', dry_run=True))

    out = capsys.readouterr().out
    assert "Move 'Nick Lodolo' to IL dry run" in out
    assert 'from_slot:         BE' in out
    assert 'to_slot:           IL' in out


def test_cmd_il_activate_reports_slot_name(monkeypatch, capsys):
    league = SimpleNamespace(
        activate_player_from_il=lambda team_id, player, slot_id, execute: {'ok': True}
    )
    team = SimpleNamespace(team_id=5)

    monkeypatch.setattr('cli.get_league', lambda: league)
    monkeypatch.setattr('cli.get_my_team', lambda _league: team)

    cmd_il_activate(SimpleNamespace(player='Nick Lodolo', slot='SP', dry_run=False))

    out = capsys.readouterr().out
    assert "Activated 'Nick Lodolo' from IL to SP." in out


def test_cmd_il_activate_unknown_slot_exits(monkeypatch):
    league = SimpleNamespace()
    team = SimpleNamespace(team_id=5)

    monkeypatch.setattr('cli.get_league', lambda: league)
    monkeypatch.setattr('cli.get_my_team', lambda _league: team)

    with pytest.raises(SystemExit) as exc:
        cmd_il_activate(SimpleNamespace(player='Nick Lodolo', slot='XYZ', dry_run=False))

    assert exc.value.code == 1
