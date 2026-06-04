from .utils import norm_id, parse_pms_rate, parse_pms_room, parse_obp


def _is_not_one(v):
    try:
        return float(v) != 1.0
    except (ValueError, TypeError):
        return True

CH_MAP = [
    {'col': 11, 'code': '19',  'name': 'Booking.com'},
    {'col': 18, 'code': '105', 'name': 'MakeMyTrip'},
    {'col': 22, 'code': '189', 'name': 'Agoda'},
    {'col': 29, 'code': '217', 'name': 'EMT'},
    {'col': 31, 'code': '351', 'name': 'CT'},
    {'col': 34, 'code': '9',   'name': 'Expedia'},
    {'col': 37, 'code': '97',  'name': 'Yatra'},
]

_CH_CODES = {ch['code'] for ch in CH_MAP}
_CH_NAME  = {ch['code']: ch['name'] for ch in CH_MAP}


def _build_dash_map(raw_rows: list) -> dict:
    """Parse dashboard raw rows → {propId: {chCode: is_live}}"""
    dash = {}
    for row in raw_rows[1:]:
        pid = norm_id(row[0]) if row else ''
        if not pid:
            continue
        status = {}
        for ch in CH_MAP:
            status[ch['code']] = (
                str(row[ch['col']]).strip() == 'Live'
                if ch['col'] < len(row) else False
            )
        dash[pid] = status
    return dash


def run_checks(su_df, crs_df, dash_raw, col_cfg):
    """
    col_cfg = {
      'su':  { 'room_id', 'rate_id', 'obp', 'prop_name', 'channel', 'app_guests' },
      'int': { 'prop_id', 'room_type', 'rate_code', 'max_occ', 'is_active' }
    }
    All values are column-name strings (or None for optional ones).
    """
    cfg_su  = col_cfg['su']
    cfg_int = col_cfg['int']

    # ── Build internal lookups ────────────────────────────────────────────
    int_rp_set  = set()   # "propId|roomType|rateCode"
    int_occ_map = {}      # "propId|roomType" → maxOcc
    int_prop_set = set()  # propId

    for _, row in crs_df.iterrows():
        if cfg_int.get('is_active'):
            v = str(row.get(cfg_int['is_active'], '')).strip().upper()
            if v != 'TRUE':
                continue

        pid = norm_id(row.get(cfg_int['prop_id'], ''))
        rt  = norm_id(row.get(cfg_int['room_type'], ''))
        rc  = norm_id(row.get(cfg_int['rate_code'], ''))
        if not pid:
            continue

        int_prop_set.add(pid)
        int_rp_set.add(f"{pid}|{rt}|{rc}")

        if cfg_int.get('max_occ'):
            try:
                mo = int(float(row.get(cfg_int['max_occ']) or 0))
            except (ValueError, TypeError):
                mo = 0
            key = f"{pid}|{rt}"
            if mo > 0 and int_occ_map.get(key, 0) < mo:
                int_occ_map[key] = mo

    # ── Build dashboard map ───────────────────────────────────────────────
    dash_map = _build_dash_map(dash_raw) if dash_raw else {}

    # ── SU tracking structures ────────────────────────────────────────────
    su_rp_set    = set()   # "propId|roomType|rateCode"
    su_rp_ch_set = set()   # "ch|propId|roomType|rateCode"
    su_rp_ch_raw = {}      # ch_key → {raw, ch_name, pname}
    su_ch_map    = set()   # "propId|ch"
    su_name_map  = {}      # propId → property name
    su_suffix_map = {}     # "propId|roomType" → suffix

    res = {k: [] for k in [
        'rr', 'obpv', 'obpoe', 'obpom',
        'rpmicp', 'rpmimap', 'rpmi', 'rpex',
        'apg', 'chlive', 'chdead', 'ncrs',
    ]}
    su_excluded = 0
    total_analyzed = 0

    # ── Main SU loop ──────────────────────────────────────────────────────
    for _, row in su_df.iterrows():
        rm  = parse_pms_room(row.get(cfg_su['room_id'], ''))
        rt  = parse_pms_rate(row.get(cfg_su['rate_id'], ''))
        obp = parse_obp(row.get(cfg_su['obp'], ''))

        pname = str(row.get(cfg_su.get('prop_name') or '', '') or '').strip()
        ch    = norm_id(row.get(cfg_su.get('channel') or '', '') or '')
        ag    = str(row.get(cfg_su.get('app_guests') or '', '') or '').strip()
        ch_name = _CH_NAME.get(ch, ch)

        # Filter: only properties in CRS data
        if not rt['propId'] or rt['propId'] not in int_prop_set:
            su_excluded += 1
            res['ncrs'].append({
                'Property ID': rt['propId'] or '(empty)',
                'Property Name': pname, 'Channel': ch,
                'PMS Room ID': rm['raw'], 'PMS Rate ID': rt['raw'],
                'Reason': 'Property ID not found in CRS data',
            })
            continue

        is_yatra = (ch == '97')

        if ch and rt['propId']:
            su_ch_map.add(f"{rt['propId']}|{ch}")
        if pname and rt['propId'] not in su_name_map:
            su_name_map[rt['propId']] = pname

        # Applicable Guests check (non-Yatra)
        if cfg_su.get('app_guests') and not is_yatra and ag:
            res['apg'].append({
                'Property ID': rt['propId'], 'Property Name': pname,
                'OTA': ch_name, 'Ch Code': ch,
                'PMS Rate ID': rt['raw'], 'Rate Plan': rt['rateCode'],
                'Applicable Guests Value': ag,
                'Issue': f'Channel {ch} has value "{ag}" in Applicable Guests — only ch 97 (Yatra) should use this',
            })

        if is_yatra:
            continue

        total_analyzed += 1

        # Check 1: Room-Rate room type mismatch
        if rm['roomType'] != rt['roomType']:
            res['rr'].append({
                'Property ID': rt['propId'], 'Property Name': pname,
                'OTA': ch_name, 'Ch Code': ch,
                'PMS Room ID': rm['raw'], 'Room Type (Room)': rm['roomType'],
                'PMS Rate ID': rt['raw'], 'Room Type (Rate)': rt['roomType'],
                'Rate Plan': rt['rateCode'],
                'Issue': f'Room ID room type "{rm["roomType"]}" ≠ Rate ID room type "{rt["roomType"]}"',
            })

        # Check 2: OBP multiplier values must all be 1
        bad_vals = [(k, v) for k, v in obp.items() if _is_not_one(v)]
        if bad_vals:
            res['obpv'].append({
                'Property ID': rt['propId'], 'Property Name': pname,
                'OTA': ch_name, 'Ch Code': ch,
                'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'],
                'Rate Plan': rt['rateCode'],
                'OBP (raw)': str(obp),
                'Bad Values': ', '.join(f'Occ {k}: {v}' for k, v in bad_vals),
                'Issue': ', '.join(f'Occ {k}: {v}' for k, v in bad_vals),
            })

        # Check 3: OBP occupancy keys vs internal max occ
        occ_key = f"{rt['propId']}|{rt['roomType']}"
        if cfg_int.get('max_occ') and occ_key in int_occ_map:
            max_occ  = int_occ_map[occ_key]
            obp_occs = sorted(int(k) for k in obp if str(k).strip().lstrip('-').isdigit())
            extra    = [o for o in obp_occs if o > max_occ]
            missing  = [o for o in range(1, max_occ + 1) if o not in obp_occs]
            base = {
                'Property ID': rt['propId'], 'Property Name': pname,
                'OTA': ch_name, 'Ch Code': ch,
                'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'],
                'Rate Plan': rt['rateCode'], 'Internal Max Occ': max_occ,
                'OBP Occupancies in SU': ', '.join(str(o) for o in obp_occs),
            }
            if extra:
                res['obpoe'].append({**base,
                    'Should Be Removed': ', '.join(str(o) for o in extra),
                    'Issue': f'Extra in SU: Occ {", ".join(str(o) for o in extra)} — internal max occ is {max_occ}',
                })
            if missing:
                res['obpom'].append({**base,
                    'Needs to be Added': ', '.join(str(o) for o in missing),
                    'Issue': f'Missing in SU: Occ {", ".join(str(o) for o in missing)} — internal max occ is {max_occ}',
                })

        # Check: SU row exists but channel not Live in dashboard
        if dash_map:
            ch_status = dash_map.get(rt['propId'])
            if ch_status and ch in ch_status and not ch_status[ch]:
                res['chdead'].append({
                    'Property ID': rt['propId'], 'Property Name': pname,
                    'OTA': ch_name, 'Ch Code': ch,
                    'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'],
                    'Rate Plan': rt['rateCode'],
                    'Internal Max Occ': int_occ_map.get(occ_key, ''),
                    'Issue': f'Mapping exists in SU but {ch_name} (ch {ch}) is not Live in dashboard',
                })

        # Track SU rate plans
        rp_key = f"{rt['propId']}|{rt['roomType']}|{rt['rateCode']}"
        ch_key = f"{ch}|{rp_key}"
        su_rp_set.add(rp_key)
        su_rp_ch_set.add(ch_key)
        su_rp_ch_raw[ch_key] = {'raw': rt['raw'], 'ch_name': ch_name, 'pname': pname}

        sfx_key = f"{rt['propId']}|{rt['roomType']}"
        if rt['suffix'] and sfx_key not in su_suffix_map:
            su_suffix_map[sfx_key] = rt['suffix']

    # ── Check 4: Rate plan coverage (per channel) ─────────────────────────
    for k in int_rp_set:
        pid, rt_id, rc = k.split('|')
        for ch_obj in CH_MAP:
            if ch_obj['code'] == '97':
                continue
            if dash_map:
                ch_status = dash_map.get(pid)
                if ch_status and ch_obj['code'] in ch_status and not ch_status[ch_obj['code']]:
                    continue  # channel not live — skip

            if f"{ch_obj['code']}|{pid}|{rt_id}|{rc}" not in su_rp_ch_set:
                sfx = su_suffix_map.get(f"{pid}|{rt_id}", '')
                entry = {
                    'Property ID': pid,
                    'Property Name': su_name_map.get(pid, ''),
                    'OTA': ch_obj['name'], 'Ch Code': ch_obj['code'],
                    'Room Type ID': rt_id, 'Rate Plan Code': rc,
                    'PMS Rate ID': f"{pid}-{rt_id}-{rc}-{sfx}" if sfx else f"{pid}-{rt_id}-{rc}",
                    'Internal Max Occ': int_occ_map.get(f"{pid}|{rt_id}", ''),
                    'Issue': 'Available internally but not pushed to SU',
                }
                rcu = rc.upper()
                if rcu in ('EP', 'CP'):
                    res['rpmicp'].append(entry)
                elif rcu in ('MAP', 'AP'):
                    res['rpmimap'].append(entry)
                else:
                    res['rpmi'].append(entry)

    # ── Check 5: Rate plan extra in SU (per channel) ──────────────────────
    for ch_key in su_rp_ch_set:
        ch, pid, rt_id, rc = ch_key.split('|')
        if pid not in int_prop_set:
            continue
        if f"{pid}|{rt_id}|{rc}" not in int_rp_set:
            d = su_rp_ch_raw.get(ch_key, {})
            res['rpex'].append({
                'Property ID': pid,
                'Property Name': d.get('pname', su_name_map.get(pid, '')),
                'OTA': d.get('ch_name', ch), 'Ch Code': ch,
                'PMS Rate ID': d.get('raw', f"{pid}-{rt_id}-{rc}"),
                'Room Type ID': rt_id, 'Rate Plan Code': rc,
                'Internal Max Occ': int_occ_map.get(f"{pid}|{rt_id}", ''),
                'Issue': 'Mapped in SU but not found internally',
            })

    # ── Check 6: OTA Live but no SU mapping ───────────────────────────────
    for prop_id, ch_status in dash_map.items():
        if prop_id not in int_prop_set:
            continue
        for ch_obj in CH_MAP:
            if ch_status.get(ch_obj['code']) and f"{prop_id}|{ch_obj['code']}" not in su_ch_map:
                res['chlive'].append({
                    'Property ID': prop_id,
                    'Property Name': su_name_map.get(prop_id, ''),
                    'OTA': ch_obj['name'], 'Ch Code': ch_obj['code'],
                    'Issue': f'{ch_obj["name"]} (ch {ch_obj["code"]}) is Live but no mapping found in SU',
                })

    res['_meta'] = {
        'crs_props':     len(int_prop_set),
        'su_excluded':   su_excluded,
        'total_analyzed': total_analyzed,
    }
    return res
