from types import SimpleNamespace

from cli import _build_roster_rows


def _player(name, slot):
    return SimpleNamespace(
        name=name,
        lineupSlot=slot,
        eligibleSlots=[slot],
        injuryStatus='',
        playerId=name,
        proTeam='FA',
    )


def test_build_roster_rows_includes_empty_available_slots():
    team = SimpleNamespace(roster=[
        _player('Catcher', 'C'),
        _player('First Base', '1B'),
        _player('Starter', 'P'),
        _player('Bench Bat', 'BE'),
    ])

    rows = _build_roster_rows(team, {0: 1, 1: 1, 5: 2, 13: 1, 16: 2, 17: 1})
    rendered = [(slot_name, getattr(player, 'name', None)) for _, slot_name, player in rows]

    assert rendered == [
        ('C', 'Catcher'),
        ('1B', 'First Base'),
        ('OF', None),
        ('OF', None),
        ('P', 'Starter'),
        ('BE', 'Bench Bat'),
        ('BE', None),
        ('IL', None),
    ]
