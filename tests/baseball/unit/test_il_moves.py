from types import SimpleNamespace
from unittest import TestCase, mock

from espn_api.baseball import League
from espn_api.requests.espn_requests import EspnFantasyRequests


class BaseballILMoveTest(TestCase):

    def setUp(self):
        with mock.patch.object(League, 'fetch_league'):
            self.league = League(league_id=1, year=2026, espn_s2='s2', swid='{SWID}')
        self.league.current_week = 13
        self.league.teams = [SimpleNamespace(
            team_id=5,
            roster=[
                SimpleNamespace(
                    name='Nick Lodolo',
                    playerId=42433,
                    lineupSlot='BE',
                    eligibleSlots=['P', 'SP', 'BE', 'IL'],
                ),
                SimpleNamespace(
                    name='Max Scherzer',
                    playerId=12345,
                    lineupSlot='IL',
                    eligibleSlots=['P', 'SP', 'BE', 'IL'],
                ),
            ],
        )]

    @mock.patch.object(EspnFantasyRequests, 'league_post')
    def test_move_player_to_il_builds_payload(self, mock_league_post):
        self.league.move_player_to_il(5, 'lodolo')

        payload = mock_league_post.call_args.kwargs['payload']
        self.assertEqual(payload['teamId'], 5)
        self.assertEqual(payload['scoringPeriodId'], 13)
        self.assertEqual(payload['memberId'], '{SWID}')
        self.assertEqual(payload['items'][0]['playerId'], 42433)
        self.assertEqual(payload['items'][0]['fromLineupSlotId'], 16)
        self.assertEqual(payload['items'][0]['toLineupSlotId'], 17)

    def test_move_player_to_il_dry_run_returns_payload(self):
        payload = self.league.move_player_to_il(5, 'lodolo', execute=False)

        self.assertEqual(payload['items'][0]['toLineupSlotId'], 17)

    @mock.patch.object(EspnFantasyRequests, 'league_post')
    def test_activate_player_from_il_defaults_to_bench(self, mock_league_post):
        self.league.activate_player_from_il(5, 'scherzer')

        payload = mock_league_post.call_args.kwargs['payload']
        self.assertEqual(payload['items'][0]['fromLineupSlotId'], 17)
        self.assertEqual(payload['items'][0]['toLineupSlotId'], 16)

    def test_activate_player_from_il_rejects_invalid_slot(self):
        with self.assertRaises(ValueError):
            self.league.activate_player_from_il(5, 'scherzer', slot_id=5, execute=False)
