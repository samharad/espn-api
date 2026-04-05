#!/Users/bert/espn-api/myenv/bin/python3
"""ESPN Fantasy Baseball CLI"""

import json
import os
import sys
import argparse
from espn_api.baseball import League

CONFIG_FILE = "espn.json"


def load_config():
    path = os.path.join(os.getcwd(), CONFIG_FILE)
    if not os.path.exists(path):
        print(f"Error: config file '{CONFIG_FILE}' not found in {os.getcwd()}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def get_my_team(league):
    cfg = load_config()
    team_id = cfg.get("team_id")
    if not team_id:
        return None
    return next((t for t in league.teams if t.team_id == int(team_id)), None)


def get_league():
    cfg = load_config()

    league_id = cfg.get("league_id")
    year = cfg.get("year")
    espn_s2 = cfg.get("espn_s2")
    swid = cfg.get("swid")

    if not league_id:
        print(f"Error: 'league_id' missing from {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)
    if not year:
        print(f"Error: 'year' missing from {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)

    return League(
        league_id=int(league_id),
        year=int(year),
        espn_s2=espn_s2,
        swid=swid,
    )


def cmd_info(args):
    league = get_league()
    s = league.settings
    print(f"League:       {s.name}")
    print(f"Year:         {league.year}")
    print(f"Teams:        {s.team_count}")
    print(f"Scoring type: {s.scoring_type}")
    print(f"Playoffs:     {s.playoff_team_count} teams")
    print(f"Current week: {league.current_week} / {league.finalScoringPeriod}")
    if s.faab:
        print(f"FAAB budget:  ${s.acquisition_budget}")


def cmd_standings(args):
    league = get_league()
    teams = league.standings()
    print(f"{'#':<4} {'Team':<30} {'W':>4} {'L':>4} {'T':>4}")
    print("-" * 46)
    for i, team in enumerate(teams, 1):
        print(f"{i:<4} {team.team_name:<30} {team.wins:>4} {team.losses:>4} {team.ties:>4}")


def cmd_scoreboard(args):
    league = get_league()
    week = args.week or league.currentMatchupPeriod
    matchups = league.scoreboard(matchupPeriod=week)
    print(f"Scoreboard — Week {week}\n")
    print(f"  {'Away':<32} {'Score':>5}    {'Score':>5}  {'Home':<32}")
    print(f"  {'-'*78}")
    for m in matchups:
        home = m.home_team.team_name if hasattr(m.home_team, 'team_name') else str(m.home_team)
        away = m.away_team.team_name if hasattr(m.away_team, 'team_name') else str(m.away_team)
        if m.home_team_live_score is not None:
            hs, as_ = f"{m.home_team_live_score:.1f}", f"{m.away_team_live_score:.1f}"
        else:
            hs, as_ = '-', '-'
        print(f"  {away:<32} {as_:>5}  vs  {hs:>5}  {home:<32}")


def cmd_boxscore(args):
    league = get_league()
    if args.week and args.week != league.currentMatchupPeriod:
        # Historical week: fall back to stale cumulativeScore data
        boxes = league.box_scores(matchup_period=args.week)
        cats = set()
        for box in boxes:
            if hasattr(box, 'home_stats') and box.home_stats:
                for cat, data in box.home_stats.items():
                    if data['result'] in ('WIN', 'LOSS'):
                        cats.add(cat)
    else:
        boxes, scored_cats = get_live_boxes(league)
        cats = set(scored_cats.keys())
    week = args.week or league.currentMatchupPeriod
    print(f"Box Scores — Week {week}\n")
    for box in boxes:
        home = box.home_team.team_name if hasattr(box.home_team, 'team_name') else str(box.home_team)
        away = box.away_team.team_name if hasattr(box.away_team, 'team_name') else str(box.away_team)
        print(f"  {away}  vs  {home}")
        home_stats = box.home_stats if hasattr(box, 'home_stats') else {}
        away_stats = box.away_stats if hasattr(box, 'away_stats') else {}
        if home_stats:
            print(f"  {'Category':<12} {'Away':>10} {'Home':>10}  {'Result'}")
            print(f"  {'-'*46}")
            for cat in sort_categories([c for c in home_stats if c in cats]):
                hdata = home_stats[cat]
                aval = away_stats.get(cat, {}).get('value', '-') if away_stats else '-'
                hval = hdata['value']
                result = hdata['result']
                print(f"  {cat:<12} {str(round(aval,2) if isinstance(aval,float) else aval):>10} {str(round(hval,2) if isinstance(hval,float) else hval):>10}  {result}")
        print()


def cmd_roster(args):
    league = get_league()
    query = args.team.lower()
    team = next(
        (t for t in league.teams if query in t.team_name.lower() or query in t.team_abbrev.lower()),
        None
    )
    if not team:
        print(f"No team matching '{args.team}'", file=sys.stderr)
        sys.exit(1)
    _print_roster(league, team, getattr(args, 'stats', None))


def cmd_my_roster(args):
    league = get_league()
    team = get_my_team(league)
    if not team:
        print("Error: TEAM_ID not set", file=sys.stderr)
        sys.exit(1)
    _print_roster(league, team, getattr(args, 'stats', None))


_BATTER_POSITIONS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH', 'UT'}
_PITCHER_POSITIONS = {'SP', 'RP', 'P'}

# Slot IDs for ESPN server-side filtering (from POSITION_MAP)
_BATTER_SLOTS  = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 19]
_PITCHER_SLOTS = [13, 14, 15]

_BATTING_SCORED  = ['R', 'HR', 'RBI', 'SB', 'OBP']
_PITCHING_SCORED = ['K', 'QS', 'SV', 'ERA', 'WHIP']

STAT_SPLITS = {
    'season': (0, 0),   # statSplitTypeId, statSourceId
    'proj':   (0, 1),
    '7':      (1, 0),
    '15':     (2, 0),
    '30':     (3, 0),
}

STAT_SPLIT_LABELS = {
    'season': '2026 Season', 'proj': '2026 Proj',
    '7': 'Last 7d', '15': 'Last 15d', '30': 'Last 30d',
}

_STAT_COL_WIDTH = {'OBP': 6, 'ERA': 6, 'WHIP': 6, 'R': 4, 'HR': 4, 'RBI': 4, 'SB': 4, 'K': 5, 'QS': 4, 'SV': 4}

# For roster position display from library's string slot names
_DISPLAY_POS_ORDER = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'DH', 'SP', 'RP']
_OF_SPECIFIC_NAMES = {'LF', 'CF', 'RF'}

# Specific slot IDs to show in position string, in display order
# C,1B,2B,3B,SS,LF,CF,RF,DH,SP,RP — skip combo/utility/bench slots
_POS_DISPLAY_SLOTS = [0, 1, 2, 3, 4, 8, 9, 10, 11, 14, 15]
_OF_SLOT = 5
_OF_SPECIFIC_SLOTS = {8, 9, 10}  # LF, CF, RF


def _eligible_positions(eligible_slot_ids):
    """Return display string of eligible positions from raw slot ID list."""
    from espn_api.baseball.constant import POSITION_MAP
    slots = set(eligible_slot_ids)
    parts = [POSITION_MAP[s] for s in _POS_DISPLAY_SLOTS if s in slots]
    if _OF_SLOT in slots and not (slots & _OF_SPECIFIC_SLOTS):
        parts.append('OF')
    return '/'.join(parts) if parts else '?'


def _format_player_positions(eligible_slot_names):
    """Format eligible positions from library string names (as in player.eligibleSlots)."""
    slots = set(eligible_slot_names)
    parts = [p for p in _DISPLAY_POS_ORDER if p in slots]
    if 'OF' in slots and not (slots & _OF_SPECIFIC_NAMES):
        parts.append('OF')
    return '/'.join(parts) if parts else '?'


_PITCHER_SLOT_NAMES = {'P', 'SP', 'RP'}
# Lineup slot IDs in display order for batters and pitchers
_BATTER_SLOT_ORDER  = [0, 1, 2, 3, 4, 6, 7, 5, 8, 9, 10, 11, 12, 16, 17]  # C→1B→2B→3B→SS→combo→OF→DH→UTIL→BE→IL
_PITCHER_SLOT_ORDER = [13, 14, 15, 16, 17]                                  # P→SP→RP→BE→IL


def _is_pitcher_player(player):
    if player.lineupSlot in _PITCHER_SLOT_NAMES:
        return True
    if player.lineupSlot in ('BE', 'IL'):
        return bool(set(player.eligibleSlots) & _PITCHER_SLOT_NAMES)
    return False


def _roster_sort_key(player):
    from espn_api.baseball.constant import POSITION_MAP
    is_p = _is_pitcher_player(player)
    slot_id = POSITION_MAP.get(player.lineupSlot, 99)
    order = _PITCHER_SLOT_ORDER if is_p else _BATTER_SLOT_ORDER
    slot_rank = order.index(slot_id) if slot_id in order else 50
    return (1 if is_p else 0, slot_rank, player.name)


def _calc_player_stats_from_raw(raw_dict):
    """Calculate final stat values including rate stats from a raw ESPN stats dict."""
    from espn_api.baseball.constant import STATS_MAP
    s = {int(k): v for k, v in raw_dict.items()}
    result = {STATS_MAP[sid]: val for sid, val in s.items() if sid in STATS_MAP}
    outs = s.get(34, 0)
    ip = outs / 3 if outs else 0
    if ip:
        result['WHIP'] = (s.get(37, 0) + s.get(39, 0)) / ip
        result['ERA'] = s.get(45, 0) * 9 / ip
    obp_den = s.get(0, 0) + s.get(10, 0) + s.get(12, 0) + s.get(13, 0)
    if obp_den:
        result['OBP'] = (s.get(1, 0) + s.get(10, 0) + s.get(12, 0)) / obp_den
    return result


def fmt_stat(val, cat):
    if not val:
        return '-'
    if cat == 'OBP':
        return f"{val:.3f}"
    if cat in ('ERA', 'WHIP'):
        return f"{val:.2f}"
    return str(int(round(val)))


def _fetch_player_stats(league, roster_players, stat_split):
    """Returns {player_id: stats_dict} for the given stat split.

    For season/proj, uses the already-fetched breakdown on each player object.
    For 7/15/30, calls kona_player_info filtered to rostered players.
    """
    if stat_split == 'season':
        return {p.playerId: p.stats.get(0, {}).get('breakdown', {}) for p in roster_players}
    if stat_split == 'proj':
        return {p.playerId: p.stats.get(0, {}).get('projected_breakdown', {}) for p in roster_players}

    # 7 / 15 / 30: fetch via kona_player_info (split types 1/2/3 not in library data)
    import json as j
    split_type_id, source_id = STAT_SPLITS[stat_split]
    player_id_set = {p.playerId for p in roster_players}
    filters = {
        'players': {
            'filterStatus': {'value': ['ONTEAM']},
            'filterSlotIds': {'value': _BATTER_SLOTS + _PITCHER_SLOTS},
            'limit': 400,
            'sortPercOwned': {'sortPriority': 1, 'sortAsc': False},
            'sortDraftRanks': {'sortPriority': 100, 'sortAsc': True, 'value': 'STANDARD'},
        }
    }
    params = {'view': 'kona_player_info', 'scoringPeriodId': league.current_week}
    headers = {'x-fantasy-filter': j.dumps(filters)}
    data = league.espn_request.league_get(params=params, headers=headers)
    result = {}
    for entry in data.get('players', []):
        player = entry.get('player', {})
        pid = player.get('id')
        if pid not in player_id_set:
            continue
        for s in player.get('stats', []):
            if s.get('statSplitTypeId') == split_type_id and s.get('statSourceId') == source_id:
                result[pid] = _calc_player_stats_from_raw(s.get('stats', {}))
                break
    return result


def _print_roster(league, team, stat_split):
    stat_cols = _BATTING_SCORED + _PITCHING_SCORED
    title = f"{team.team_name} — Roster"
    if stat_split:
        title += f" — {STAT_SPLIT_LABELS[stat_split]}"
    print(f"{title}\n")

    roster = sorted(team.roster, key=_roster_sort_key)

    pos_w = max((_format_player_positions(p.eligibleSlots) for p in roster), key=len, default='Pos')
    pos_w = max(len(pos_w), 3)

    stat_map = {}
    if stat_split:
        stat_map = _fetch_player_stats(league, roster, stat_split)

    stat_header = '  '.join(f"{c:>{_STAT_COL_WIDTH.get(c, 4)}}" for c in stat_cols)
    if stat_split:
        print(f"  {'Name':<25} {'Pos':<{pos_w}} {'Slot':<6} {'Team':<5} {stat_header}  Status")
        sep_len = 25 + pos_w + 6 + 5 + sum(_STAT_COL_WIDTH.get(c, 4) + 2 for c in stat_cols) + 9
    else:
        print(f"  {'Name':<25} {'Pos':<{pos_w}} {'Slot':<6} {'Team':<6} Status")
        sep_len = 25 + pos_w + 6 + 6 + 10
    print(f"  {'-' * sep_len}")

    last_group = None
    for player in roster:
        group = 1 if _is_pitcher_player(player) else 0
        if last_group is not None and group != last_group:
            print()
        last_group = group

        pos = _format_player_positions(player.eligibleSlots)
        status = player.injuryStatus or ''
        if status == 'ACTIVE':
            status = ''
        if stat_split:
            stats = stat_map.get(player.playerId, {})
            stat_vals = '  '.join(f"{fmt_stat(stats.get(c), c):>{_STAT_COL_WIDTH.get(c, 4)}}" for c in stat_cols)
            print(f"  {player.name:<25} {pos:<{pos_w}} {player.lineupSlot:<6} {str(player.proTeam):<5} {stat_vals}  {status}")
        else:
            print(f"  {player.name:<25} {pos:<{pos_w}} {player.lineupSlot:<6} {str(player.proTeam):<6} {status}")


def cmd_players(args):
    import json as j
    from espn_api.baseball.constant import POSITION_MAP, PRO_TEAM_MAP

    league = get_league()
    pos = args.position
    stat_split = getattr(args, 'stats', None)
    player_filter = getattr(args, 'filter', 'available')
    pos_lower = (pos or '').lower()

    # Resolve position → slot filter, display label, stat columns
    if pos_lower == 'batters':
        slot_filter, pos_label = _BATTER_SLOTS, 'Batters'
        stat_cols = _BATTING_SCORED
    elif pos_lower == 'pitchers':
        slot_filter, pos_label = _PITCHER_SLOTS, 'Pitchers'
        stat_cols = _PITCHING_SCORED
    elif pos and pos.upper() in POSITION_MAP:
        slot_filter = [POSITION_MAP[pos.upper()]]
        pos_label = pos.upper()
        stat_cols = _PITCHING_SCORED if pos.upper() in ('SP', 'RP', 'P') else _BATTING_SCORED
    else:
        slot_filter, pos_label = [], 'All'
        stat_cols = _BATTING_SCORED + _PITCHING_SCORED

    # Always use raw API so position uses eligible slots (library's defaultPositionId is unreliable)
    split_type_id, source_id = STAT_SPLITS.get(stat_split, (None, None))
    params = {'view': 'kona_player_info', 'scoringPeriodId': league.current_week}
    filters = {
        'players': {
            'filterStatus': {'value': {'available': ['FREEAGENT', 'WAIVERS'], 'rostered': ['ONTEAM'], 'all': ['FREEAGENT', 'WAIVERS', 'ONTEAM']}[player_filter]},
            'filterSlotIds': {'value': slot_filter},
            'limit': args.size,
            'sortPercOwned': {'sortPriority': 1, 'sortAsc': False},
            'sortDraftRanks': {'sortPriority': 100, 'sortAsc': True, 'value': 'STANDARD'},
        }
    }
    headers = {'x-fantasy-filter': j.dumps(filters)}
    data = league.espn_request.league_get(params=params, headers=headers)

    rows = []
    for entry in data.get('players', []):
        player = entry.get('player', {})
        position = _eligible_positions(player.get('eligibleSlots', []))
        pro_team = str(PRO_TEAM_MAP.get(player.get('proTeamId', 0), '?'))
        pct_owned = round(player.get('ownership', {}).get('percentOwned', 0), 1)
        injury = player.get('injuryStatus') or ''
        if injury == 'ACTIVE':
            injury = ''
        player_stats = {}
        if split_type_id is not None:
            for s in player.get('stats', []):
                if s.get('statSplitTypeId') == split_type_id and s.get('statSourceId') == source_id:
                    player_stats = _calc_player_stats_from_raw(s.get('stats', {}))
                    break
        rows.append((player.get('fullName', '?'), position, pro_team, pct_owned, injury, player_stats))

    filter_label = {'available': 'Available', 'rostered': 'Rostered', 'all': 'All'}[player_filter]
    title = f"Players — {filter_label} — {pos_label}"
    if stat_split:
        title += f" — {STAT_SPLIT_LABELS[stat_split]}"
    print(f"{title} (top {len(rows)})\n")

    pos_w = max(len(r[1]) for r in rows) if rows else 3
    pos_w = max(pos_w, 3)

    if stat_split:
        stat_header = '  '.join(f"{c:>{_STAT_COL_WIDTH.get(c, 4)}}" for c in stat_cols)
        print(f"  {'Name':<25} {'Pos':<{pos_w}} {'Team':<5} {'%Own':>5}  {stat_header}  Status")
        print(f"  {'-' * (25 + pos_w + 5 + 6 + sum(_STAT_COL_WIDTH.get(c, 4) + 2 for c in stat_cols) + 8)}")
        for name, position, pro_team, pct_owned, injury, stats in rows:
            stat_vals = '  '.join(f"{fmt_stat(stats.get(c), c):>{_STAT_COL_WIDTH.get(c, 4)}}" for c in stat_cols)
            print(f"  {name:<25} {position:<{pos_w}} {pro_team:<5} {pct_owned:>4.1f}%  {stat_vals}  {injury}")
    else:
        print(f"  {'Name':<25} {'Pos':<{pos_w}} {'Team':<6} {'%Own':>6}  Status")
        print(f"  {'-' * (25 + 1 + pos_w + 1 + 6 + 7 + 8)}")
        for name, position, pro_team, pct_owned, injury, stats in rows:
            print(f"  {name:<25} {position:<{pos_w}} {pro_team:<6} {pct_owned:>5.1f}%  {injury}")


def cmd_activity(args):
    import datetime
    league = get_league()
    activities = league.recent_activity(size=args.size)
    print(f"Recent Activity (last {len(activities)})\n")
    for act in activities:
        ts = datetime.datetime.fromtimestamp(act.date / 1000).strftime('%Y-%m-%d %H:%M')
        for team, action, player in act.actions:
            team_name = team.team_name if hasattr(team, 'team_name') else str(team)
            print(f"  {ts}  {action:<10}  {str(player):<25}  {team_name}")


def cmd_schedule(args):
    league = get_league()
    query = args.team.lower()
    team = next(
        (t for t in league.teams if query in t.team_name.lower() or query in t.team_abbrev.lower()),
        None
    )
    if not team:
        print(f"No team matching '{args.team}'", file=sys.stderr)
        sys.exit(1)
    print(f"{team.team_name} — Schedule\n")
    print(f"  {'Wk':<4} {'Opponent':<30} {'Result'}")
    print(f"  {'-'*50}")
    for week, matchup in enumerate(team.schedule, 1):
        home = matchup.home_team
        away = matchup.away_team
        if hasattr(home, 'team_id') and home.team_id == team.team_id:
            opponent = away.team_name if hasattr(away, 'team_name') else str(away)
        else:
            opponent = home.team_name if hasattr(home, 'team_name') else str(home)
        winner = getattr(matchup, 'winner', None)
        if winner == 'HOME' and hasattr(home, 'team_id') and home.team_id == team.team_id:
            result = 'W'
        elif winner == 'AWAY' and hasattr(away, 'team_id') and away.team_id == team.team_id:
            result = 'W'
        elif winner == 'UNDECIDED' or winner is None:
            result = '-'
        else:
            result = 'L'
        print(f"  {week:<4} {opponent:<30} {result}")


PITCHING_CATS = {
    'OUTS', 'TBF', 'P', 'P_H', 'OBA', 'P_BB', 'P_IBB', 'WHIP', 'OOBP',
    'P_R', 'ER', 'P_HR', 'ERA', 'K', 'K/9', 'WP', 'BLK', 'PK', 'W', 'L',
    'WPCT', 'SVO', 'SV', 'BLSV', 'SV%', 'HLD', 'CG', 'QS', 'NH', 'PG',
    'K/BB', 'SVHD', 'GP', 'GS',
}


PITCHING_ORDER = ['K', 'QS', 'SV', 'ERA', 'WHIP']


def sort_categories(cats):
    """Return categories sorted: batting first, then pitching in standard order."""
    batting = [c for c in cats if c not in PITCHING_CATS]
    pitching_ordered = [c for c in PITCHING_ORDER if c in cats]
    pitching_rest = [c for c in cats if c in PITCHING_CATS and c not in PITCHING_ORDER]
    return batting + pitching_ordered + pitching_rest


# Stat IDs for rate-stat components (not scored directly but needed for calculation)
_RATE_COMPONENT_IDS = {
    0, 1, 10, 12, 13,   # OBP: AB, H, B_BB, HBP, SF
    34, 37, 39, 45,      # ERA/WHIP: OUTS, P_H, P_BB, ER
}


def _make_live_api_call(league):
    """Single API call returning settings + live roster stats for current matchup."""
    import json as j
    params = {
        'view': ['mSettings', 'mMatchupScore', 'mScoreboard', 'mRoster'],
        'scoringPeriodId': league.current_week,
    }
    filters = {"schedule": {"filterMatchupPeriodIds": {"value": [league.currentMatchupPeriod]}}}
    headers = {'x-fantasy-filter': j.dumps(filters)}
    return league.espn_request.league_get(params=params, headers=headers)


def _parse_scored_cats(data):
    """Extract {cat_name: is_reverse} from API response settings."""
    from espn_api.baseball.constant import STATS_MAP
    items = data['settings']['scoringSettings']['scoringItems']
    return {STATS_MAP[item['statId']]: item['isReverseItem']
            for item in items if item['statId'] in STATS_MAP}


def _sum_live_stats(team_data, scored_stat_ids):
    """Sum stats from rosterForMatchupPeriod; calculate OBP/ERA/WHIP from components."""
    from espn_api.baseball.constant import STATS_MAP
    all_ids = scored_stat_ids | _RATE_COMPONENT_IDS
    totals = {}
    for entry in team_data.get('rosterForMatchupPeriod', {}).get('entries', []):
        player = entry.get('playerPoolEntry', {}).get('player', {})
        for stat_entry in player.get('stats', []):
            for sid_str, val in stat_entry.get('stats', {}).items():
                sid = int(sid_str)
                if sid in all_ids:
                    totals[sid] = totals.get(sid, 0) + val

    result = {STATS_MAP[sid]: val for sid, val in totals.items() if sid in STATS_MAP}

    outs = totals.get(34, 0)
    ip = outs / 3 if outs else 0
    if ip:
        result['WHIP'] = (totals.get(37, 0) + totals.get(39, 0)) / ip
        result['ERA'] = totals.get(45, 0) * 9 / ip

    obp_den = totals.get(0, 0) + totals.get(10, 0) + totals.get(12, 0) + totals.get(13, 0)
    if obp_den:
        result['OBP'] = (totals.get(1, 0) + totals.get(10, 0) + totals.get(12, 0)) / obp_den

    return result


class LiveBox:
    """Box score built from live rosterForMatchupPeriod stats."""

    def __init__(self, home_team, away_team, home_raw, away_raw, scored_cats):
        self.home_team = home_team
        self.away_team = away_team
        self.home_stats = {}
        self.away_stats = {}
        self.home_wins = self.home_losses = self.home_ties = 0
        self.away_wins = self.away_losses = self.away_ties = 0

        for cat, is_reverse in scored_cats.items():
            hval = home_raw.get(cat)
            aval = away_raw.get(cat)
            if hval is None or aval is None:
                hr = ar = None
            elif hval == aval:
                hr = ar = 'TIE'
                self.home_ties += 1
                self.away_ties += 1
            elif (hval < aval) == is_reverse:
                hr, ar = 'WIN', 'LOSS'
                self.home_wins += 1
                self.away_losses += 1
            else:
                hr, ar = 'LOSS', 'WIN'
                self.home_losses += 1
                self.away_wins += 1
            self.home_stats[cat] = {'value': hval, 'result': hr}
            self.away_stats[cat] = {'value': aval, 'result': ar}


def get_live_boxes(league):
    """Returns (list[LiveBox], scored_cats_dict) with live stats from ESPN roster data."""
    from espn_api.baseball.constant import STATS_MAP
    rev_map = {v: k for k, v in STATS_MAP.items()}

    data = _make_live_api_call(league)
    scored_cats = _parse_scored_cats(data)
    scored_stat_ids = {rev_map[cat] for cat in scored_cats if cat in rev_map}

    team_by_id = {t.team_id: t for t in league.teams}
    boxes = []
    for m in data.get('schedule', []):
        home_data = m.get('home', {})
        away_data = m.get('away', {})
        home_team = team_by_id.get(home_data.get('teamId'), home_data.get('teamId'))
        away_team = team_by_id.get(away_data.get('teamId'), away_data.get('teamId'))
        home_raw = _sum_live_stats(home_data, scored_stat_ids)
        away_raw = _sum_live_stats(away_data, scored_stat_ids)
        boxes.append(LiveBox(home_team, away_team, home_raw, away_raw, scored_cats))

    return boxes, scored_cats


def print_matchup(box, scored_cats=None):
    home_name = box.home_team.team_name if hasattr(box.home_team, 'team_name') else str(box.home_team)
    away_name = box.away_team.team_name if hasattr(box.away_team, 'team_name') else str(box.away_team)
    if hasattr(box, 'home_stats') and box.home_stats:
        away_record = f"{box.away_wins}-{box.away_losses}-{box.away_ties}"
        home_record = f"{box.home_wins}-{box.home_losses}-{box.home_ties}"
        print(f"  {away_name} ({away_record})  vs  {home_name} ({home_record})\n")
        col = 20
        print(f"  {'Category':<12} {away_name:>{col}} {home_name:>{col}}  {'Winner'}")
        print(f"  {'-'*(12 + col*2 + 12)}")
        ordered = sort_categories([c for c in box.home_stats if scored_cats is None or c in scored_cats])
        for cat in ordered:
            hdata = box.home_stats[cat]
            aval = box.away_stats.get(cat, {}).get('value', '-') if box.away_stats else '-'
            hval = hdata['value']
            result = hdata['result']  # WIN/LOSS/TIE from home team's perspective
            if result == 'WIN':
                winner = home_name
            elif result == 'LOSS':
                winner = away_name
            else:
                winner = 'TIE'
            prec = 4 if cat in ('OBP', 'OOBP') else 3 if cat in ('ERA', 'WHIP', 'K/9', 'K/BB', 'SV%') else 0
            astr = f"{aval:.{prec}f}" if isinstance(aval, float) else str(aval)
            hstr = f"{hval:.{prec}f}" if isinstance(hval, float) else str(hval)
            print(f"  {cat:<12} {astr:>{col}} {hstr:>{col}}  {winner}")
    else:
        print(f"  {away_name}  vs  {home_name}  (no stats yet)")


def cmd_my_matchup(args):
    league = get_league()
    team = get_my_team(league)
    if not team:
        print("Error: TEAM_ID not set", file=sys.stderr)
        sys.exit(1)
    boxes, _ = get_live_boxes(league)
    box = next((b for b in boxes if
                (hasattr(b.home_team, 'team_id') and b.home_team.team_id == team.team_id) or
                (hasattr(b.away_team, 'team_id') and b.away_team.team_id == team.team_id)), None)
    if not box:
        print("No current matchup found.", file=sys.stderr)
        sys.exit(1)
    print(f"Your Matchup — Week {league.currentMatchupPeriod}\n")
    print_matchup(box)


def cmd_matchup(args):
    league = get_league()
    query = args.team.lower()
    team = next(
        (t for t in league.teams if query in t.team_name.lower() or query in t.team_abbrev.lower()),
        None
    )
    if not team:
        print(f"No team matching '{args.team}'", file=sys.stderr)
        sys.exit(1)
    boxes, _ = get_live_boxes(league)
    box = next((b for b in boxes if
                (hasattr(b.home_team, 'team_id') and b.home_team.team_id == team.team_id) or
                (hasattr(b.away_team, 'team_id') and b.away_team.team_id == team.team_id)), None)
    if not box:
        print(f"No current matchup found for '{team.team_name}'.", file=sys.stderr)
        sys.exit(1)
    print(f"{team.team_name} — Matchup Week {league.currentMatchupPeriod}\n")
    print_matchup(box)


def cmd_compare(args):
    league = get_league()

    def find_team(query):
        q = query.lower()
        return next((t for t in league.teams if q in t.team_name.lower() or q in t.team_abbrev.lower()), None)

    t1 = find_team(args.team1)
    t2 = find_team(args.team2)
    if not t1:
        print(f"No team matching '{args.team1}'", file=sys.stderr); sys.exit(1)
    if not t2:
        print(f"No team matching '{args.team2}'", file=sys.stderr); sys.exit(1)

    # Find a box score between these two teams
    boxes, _ = get_live_boxes(league)
    box = next((b for b in boxes if
                {getattr(b.home_team, 'team_id', None), getattr(b.away_team, 'team_id', None)} ==
                {t1.team_id, t2.team_id}), None)

    if box and box.home_stats:
        home = box.home_team
        t1_is_home = hasattr(home, 'team_id') and home.team_id == t1.team_id
        if t1_is_home:
            r1 = f"{box.home_wins}-{box.home_losses}-{box.home_ties}"
            r2 = f"{box.away_wins}-{box.away_losses}-{box.away_ties}"
        else:
            r1 = f"{box.away_wins}-{box.away_losses}-{box.away_ties}"
            r2 = f"{box.home_wins}-{box.home_losses}-{box.home_ties}"
        col = 22
        print(f"  {t1.team_name} ({r1})  vs  {t2.team_name} ({r2})\n")
        print(f"  {'Category':<12} {t1.team_name:>{col}} {t2.team_name:>{col}}  {'Winner'}")
        print(f"  {'-'*(12 + col*2 + 12)}")
        ordered = sort_categories(list(box.home_stats.keys()))
        for cat in ordered:
            hdata = box.home_stats[cat]
            hval = hdata['value']
            aval = box.away_stats.get(cat, {}).get('value', '-') if box.away_stats else '-'
            result = hdata['result']  # WIN/LOSS/TIE from home team's perspective
            if result == 'WIN':
                winner = t1.team_name if t1_is_home else t2.team_name
            elif result == 'LOSS':
                winner = t2.team_name if t1_is_home else t1.team_name
            else:
                winner = 'TIE'
            v1 = hval if t1_is_home else aval
            v2 = aval if t1_is_home else hval
            v1s = str(round(v1, 2) if isinstance(v1, float) else v1)
            v2s = str(round(v2, 2) if isinstance(v2, float) else v2)
            print(f"  {cat:<12} {v1s:>{col}} {v2s:>{col}}  {winner}")
    else:
        print(f"  {t1.team_name}  vs  {t2.team_name}  (not currently matched up — no live comparison available)")


def cmd_my_schedule(args):
    league = get_league()
    team = get_my_team(league)
    if not team:
        print("Error: TEAM_ID not set", file=sys.stderr)
        sys.exit(1)
    print(f"{team.team_name} — Schedule\n")
    print(f"  {'Wk':<4} {'Opponent':<30} {'Result'}")
    print(f"  {'-'*50}")
    for week, matchup in enumerate(team.schedule, 1):
        home = matchup.home_team
        away = matchup.away_team
        opponent = (away.team_name if hasattr(away, 'team_name') else str(away)) \
            if (hasattr(home, 'team_id') and home.team_id == team.team_id) \
            else (home.team_name if hasattr(home, 'team_name') else str(home))
        winner = getattr(matchup, 'winner', None)
        if winner == 'HOME' and hasattr(home, 'team_id') and home.team_id == team.team_id:
            result = 'W'
        elif winner == 'AWAY' and hasattr(away, 'team_id') and away.team_id == team.team_id:
            result = 'W'
        elif winner == 'UNDECIDED' or winner is None:
            result = '-'
        else:
            result = 'L'
        print(f"  {week:<4} {opponent:<30} {result}")


def cmd_teams(args):
    league = get_league()
    print(f"{'ID':<4} {'Abbrev':<8} {'Team':<30} {'Division'}")
    print("-" * 60)
    for team in league.teams:
        print(f"{team.team_id:<4} {team.team_abbrev:<8} {team.team_name:<30} {team.division_name}")


POLL_STATE_FILE = "matchup-poll-state.json"


def cmd_poll_matchup(args):
    league = get_league()
    team = get_my_team(league)
    if not team:
        print("Error: team_id not set in espn.json", file=sys.stderr)
        sys.exit(1)

    boxes, _ = get_live_boxes(league)
    box = next((b for b in boxes if
                (hasattr(b.home_team, 'team_id') and b.home_team.team_id == team.team_id) or
                (hasattr(b.away_team, 'team_id') and b.away_team.team_id == team.team_id)), None)

    if not box or not box.home_stats:
        return  # no data, nothing to report

    # Determine orientation — is my team home or away?
    my_is_home = hasattr(box.home_team, 'team_id') and box.home_team.team_id == team.team_id
    opponent = box.away_team if my_is_home else box.home_team
    opponent_name = opponent.team_name if hasattr(opponent, 'team_name') else str(opponent)

    # Build current state: per-category result from my team's perspective
    # LiveBox stores results from home team's perspective; flip if I'm away
    stats = box.home_stats if my_is_home else box.away_stats
    current_cats = {cat: data['result'] for cat, data in stats.items() if data['result']}

    my_wins = sum(1 for r in current_cats.values() if r == 'WIN')
    my_losses = sum(1 for r in current_cats.values() if r == 'LOSS')
    my_ties = sum(1 for r in current_cats.values() if r == 'TIE')

    current_state = {
        'week': league.currentMatchupPeriod,
        'wins': my_wins,
        'losses': my_losses,
        'ties': my_ties,
        'categories': current_cats,
    }

    # Load previous state
    import time
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), POLL_STATE_FILE)
    prev_state = None
    if os.path.exists(state_path):
        with open(state_path) as f:
            prev_state = json.load(f)

    # Build sliding window: keep last hour of snapshots
    now = time.time()
    cutoff = now - 3600
    history = [e for e in (prev_state or {}).get('history', []) if e['ts'] >= cutoff]
    history.append({
        'ts': int(now),
        'wins': my_wins,
        'losses': my_losses,
        'ties': my_ties,
        'categories': current_cats,
    })
    current_state['history'] = history

    # Save current state
    with open(state_path, 'w') as f:
        json.dump(current_state, f, indent=2)

    # First run or new week — no notification, just initialize
    if prev_state is None or prev_state.get('week') != current_state['week']:
        return

    # Check for changes
    prev_cats = prev_state.get('categories', {})
    i_took    = [c for c in current_cats if current_cats[c] == 'WIN' and prev_cats.get(c) != 'WIN']
    they_took = [c for c in current_cats if current_cats[c] == 'LOSS' and prev_cats.get(c) != 'LOSS']
    now_tied  = [c for c in current_cats if current_cats[c] == 'TIE' and prev_cats.get(c) != 'TIE']

    if not i_took and not they_took and not now_tied:
        return  # no change, print nothing

    score = f"{my_wins}-{my_losses}-{my_ties}"
    parts = [f"Matchup score vs {opponent_name} is now {score}."]
    if they_took:
        parts.append(f"{opponent_name} took: {', '.join(they_took)}.")
    if i_took:
        parts.append(f"You took: {', '.join(i_took)}.")
    if now_tied:
        parts.append(f"Now tied: {', '.join(now_tied)}.")
    print(' '.join(parts))


def cmd_power_rankings(args):
    league = get_league()
    boxes, scored_cats = get_live_boxes(league)

    # Collect raw stat values for every team
    team_stats = {}  # {team_abbrev: {cat: value}}
    for box in boxes:
        for team, stats in [(box.home_team, box.home_stats), (box.away_team, box.away_stats)]:
            abbrev = team.team_abbrev if hasattr(team, 'team_abbrev') else str(team)
            team_stats[abbrev] = {cat: data['value'] for cat, data in stats.items() if data['value'] is not None}

    cats = sort_categories(list(scored_cats.keys()))
    teams = sorted(team_stats.keys())

    # Rank all teams in each category; ties share the average of the positions they occupy
    cat_points = {t: {} for t in teams}
    for cat in cats:
        is_reverse = scored_cats[cat]
        values = [(t, team_stats[t][cat]) for t in teams if cat in team_stats[t]]
        values.sort(key=lambda x: x[1], reverse=not is_reverse)  # best first
        i = 0
        while i < len(values):
            j = i
            while j + 1 < len(values) and values[j + 1][1] == values[i][1]:
                j += 1
            # positions i..j (0-indexed) share points; points = len(values) down to 1
            n = len(values)
            pts = sum(n - k for k in range(i, j + 1)) / (j - i + 1)
            for k in range(i, j + 1):
                cat_points[values[k][0]][cat] = pts
            i = j + 1

    totals = {t: sum(cat_points[t].values()) for t in teams}
    ranked = sorted(teams, key=lambda t: totals[t], reverse=True)

    # Format points: show integer if whole, else one decimal
    def fmt(v):
        return str(int(v)) if v == int(v) else f"{v:.1f}"

    # Header
    cat_w = 5
    name_w = 22
    total_w = 6
    header = f"  {'#':<3} {'Team':<{name_w}} {'Total':>{total_w}}  " + "  ".join(f"{c:>{cat_w}}" for c in cats)
    print(f"Weekly Power Rankings — Week {league.currentMatchupPeriod}\n")
    print(header)
    print("  " + "─" * (len(header) - 2))

    for rank, abbrev in enumerate(ranked, 1):
        total = fmt(totals[abbrev])
        pts_cols = "  ".join(f"{fmt(cat_points[abbrev].get(c, 0)):>{cat_w}}" for c in cats)
        print(f"  {rank:<3} {abbrev:<{name_w}} {total:>{total_w}}  {pts_cols}")


def cmd_help(args):
    commands = [
        ("League", [
            ("info",            "",                         "League name, scoring type, team count, current week, playoff info"),
            ("standings",       "",                         "W/L/T table for all teams, sorted by current rank"),
            ("teams",           "",                         "All teams with ID, abbreviation, and division"),
        ]),
        ("Matchups & Scores", [
            ("scoreboard",      "[--week N]",               "Score for each matchup this week (or week N)"),
            ("boxscore",        "[--week N]",               "Category-by-category results for every matchup"),
            ("matchup",         "<team>",                   "Current matchup for a specific team with full category breakdown"),
            ("my-matchup",      "",                         "Your current matchup (uses TEAM_ID)"),
            ("compare",         "<team1> <team2>",          "Side-by-side category comparison (must be matched up this week)"),
            ("power-rankings",  "",                         "All teams ranked by category points this week (league-wide)"),
        ]),
        ("Rosters & Players", [
            ("roster",          "<team> [-s SPLIT]",        "Roster sorted batters-first then pitchers (active→bench→IL). -s: season/proj/7/15/30"),
            ("my-roster",       "[-s SPLIT]",               "Your roster (uses TEAM_ID). Same sort and -s options as roster"),
            ("players",         "[-f F] [-p POS] [-s S] [-n N]", "Browse players. -f: available/rostered/all. -p: C/1B/2B/3B/SS/OF/DH/SP/RP/batters/pitchers. -s: season/proj/7/15/30"),
        ]),
        ("Schedule & Activity", [
            ("schedule",        "<team>",                   "Full season schedule for any team"),
            ("my-schedule",     "",                         "Your full season schedule (uses TEAM_ID)"),
            ("activity",        "[-n N]",                   "Recent adds, drops, and trades league-wide (default: 25)"),
        ]),
    ]

    print("ESPN Fantasy Baseball CLI\n")
    print("Usage: python cli.py <command> [options]\n")
    print("Team arguments accept partial name or abbreviation matches (e.g. 'Dons', 'batGPT').\n")
    print("Config: espn.json in the current directory. Required keys: league_id, year, espn_s2, swid. Optional: team_id (for my-* commands)\n")

    for section, cmds in commands:
        print(f"{section}")
        print(f"  {'Command':<16} {'Args':<25} Description")
        print(f"  {'-'*75}")
        for name, usage, desc in cmds:
            print(f"  {name:<16} {usage:<25} {desc}")
        print()


def main():
    parser = argparse.ArgumentParser(
        prog="espn",
        description="ESPN Fantasy Baseball CLI",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    sub.add_parser("info", help="Show league info and settings")
    sub.add_parser("standings", help="Show current standings")
    sub.add_parser("teams", help="List all teams")
    p_scoreboard = sub.add_parser("scoreboard", help="Show matchups for a week")
    p_scoreboard.add_argument("--week", type=int, default=None, help="Matchup period (default: current)")
    p_boxscore = sub.add_parser("boxscore", help="Show category box scores for a week")
    p_boxscore.add_argument("--week", type=int, default=None, help="Matchup period (default: current)")
    p_roster = sub.add_parser("roster", help="Show a team's roster")
    p_roster.add_argument("team", help="Team name or abbreviation (partial match)")
    p_roster.add_argument("--stats", "-s", default=None, choices=['season', 'proj', '7', '15', '30'],
                          help="Show stat columns: season, proj, 7, 15, or 30 (days)")
    p_fa = sub.add_parser("players", help="Browse players by availability, position, and stats")
    p_fa.add_argument("--filter", "-f", default="available", choices=["available", "rostered", "all"],
                      help="available (default), rostered, or all")
    p_fa.add_argument("--position", "-p", default=None, help="Position filter (C, 1B, SP, RP, batters, pitchers, ...)")
    p_fa.add_argument("--size", "-n", type=int, default=25, help="Number of results (default: 25)")
    p_fa.add_argument("--stats", "-s", default=None, choices=['season', 'proj', '7', '15', '30'],
                      help="Show stat columns: season, proj, 7, 15, or 30 (days)")
    p_activity = sub.add_parser("activity", help="Show recent adds, drops, and trades")
    p_activity.add_argument("--size", "-n", type=int, default=25, help="Number of transactions (default: 25)")
    p_schedule = sub.add_parser("schedule", help="Show a team's full schedule")
    p_schedule.add_argument("team", help="Team name or abbreviation (partial match)")
    sub.add_parser("power-rankings", help="Weekly power rankings: all teams ranked by category points")
    sub.add_parser("help", help="Show detailed help for all commands")
    p_my_roster = sub.add_parser("my-roster", help="Show your roster (requires TEAM_ID)")
    p_my_roster.add_argument("--stats", "-s", default=None, choices=['season', 'proj', '7', '15', '30'],
                              help="Show stat columns: season, proj, 7, 15, or 30 (days)")
    sub.add_parser("my-schedule", help="Show your schedule (requires TEAM_ID)")
    sub.add_parser("my-matchup", help="Show your current matchup (requires TEAM_ID)")
    sub.add_parser("poll-matchup", help="Print a notification if matchup score changed since last poll (for cron use)")
    p_matchup = sub.add_parser("matchup", help="Show a team's current matchup")
    p_matchup.add_argument("team", help="Team name or abbreviation (partial match)")
    p_compare = sub.add_parser("compare", help="Compare two teams head-to-head")
    p_compare.add_argument("team1", help="First team (partial match)")
    p_compare.add_argument("team2", help="Second team (partial match)")

    args = parser.parse_args()

    commands = {
        "info": cmd_info,
        "standings": cmd_standings,
        "teams": cmd_teams,
        "scoreboard": cmd_scoreboard,
        "boxscore": cmd_boxscore,
        "roster": cmd_roster,
        "players": cmd_players,
        "activity": cmd_activity,
        "schedule": cmd_schedule,
        "help": cmd_help,
        "my-roster": cmd_my_roster,
        "my-schedule": cmd_my_schedule,
        "my-matchup": cmd_my_matchup,
        "matchup": cmd_matchup,
        "compare": cmd_compare,
        "poll-matchup": cmd_poll_matchup,
        "power-rankings": cmd_power_rankings,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
