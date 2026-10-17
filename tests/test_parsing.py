from datetime import datetime

import pytest

from jira_time_logger.parsing import (JIRA_KEY_PATTERN, adjust_datetime, format_duration,
                                      is_blank, parse_time_range, row_total_seconds,
                                      truncate, validate_row)


class TestParseTimeRange:
    def test_simple_range(self):
        start, end, duration = parse_time_range('9:00 am - 5:00 pm')
        assert duration == 8 * 3600
        assert start.hour == 9
        assert end.hour == 17

    def test_minutes(self):
        assert parse_time_range('9:05 am - 9:20 am')[2] == 15 * 60

    def test_overnight_range_crosses_midnight(self):
        assert parse_time_range('11:00 pm - 1:00 am')[2] == 2 * 3600

    def test_strips_whitespace(self):
        assert parse_time_range('  9:00 am - 10:00 am  ')[2] == 3600

    def test_zero_length_range_rejected(self):
        with pytest.raises(ValueError, match='zero-length'):
            parse_time_range('9:00 am - 9:00 am')

    def test_missing_end_time_rejected(self):
        with pytest.raises(ValueError, match='invalid time range'):
            parse_time_range('11:20 am')

    def test_three_times_rejected(self):
        with pytest.raises(ValueError, match='invalid time range'):
            parse_time_range('4:50 pm - 5:15 pm - 5:50 pm')

    def test_open_ended_range_rejected(self):
        with pytest.raises(ValueError):
            parse_time_range('2:15 pm -')

    def test_bad_format_rejected(self):
        with pytest.raises(ValueError):
            parse_time_range('9am - 10am')


class TestAdjustDatetime:
    def test_est_conversion(self):
        # January 5th is EST (UTC-5)
        time_obj = datetime.strptime('7:00 AM', '%I:%M %p')
        assert adjust_datetime('1/5/26', time_obj, 'America/New_York') == \
            '2026-01-05T12:00:00.000+0000'

    def test_edt_conversion(self):
        # July 6th is EDT (UTC-4)
        time_obj = datetime.strptime('7:00 AM', '%I:%M %p')
        assert adjust_datetime('7/6/26', time_obj, 'America/New_York') == \
            '2026-07-06T11:00:00.000+0000'

    def test_bad_date_rejected(self):
        time_obj = datetime.strptime('7:00 AM', '%I:%M %p')
        with pytest.raises(ValueError):
            adjust_datetime('2026-01-05', time_obj, 'America/New_York')


class TestValidateRow:
    def test_single_range(self):
        row = {'Date': '1/5/26', 'Times': '7:00 am - 8:00 am'}
        entries = validate_row(row, 'America/New_York')
        assert entries == [('2026-01-05T12:00:00.000+0000', 3600)]

    def test_multiple_ranges(self):
        row = {'Date': '1/5/26', 'Times': '7:00 am - 8:00 am --- 9:00 am - 9:30 am'}
        entries = validate_row(row, 'America/New_York')
        assert len(entries) == 2
        assert entries[1] == ('2026-01-05T14:00:00.000+0000', 1800)

    def test_any_bad_range_fails_the_whole_row(self):
        row = {'Date': '1/5/26', 'Times': '7:00 am - 8:00 am --- 2:15 pm -'}
        with pytest.raises(ValueError):
            validate_row(row, 'America/New_York')


class TestRowTotalSeconds:
    def test_sums_all_ranges(self):
        row = {'Times': '7:00 am - 8:00 am --- 9:00 am - 9:30 am'}
        assert row_total_seconds(row) == 5400

    def test_raises_on_bad_data(self):
        with pytest.raises(ValueError):
            row_total_seconds({'Times': 'nonsense'})


class TestJiraKeyPattern:
    @pytest.mark.parametrize('key', ['EL-36031', 'AB-1', 'A2C-123'])
    def test_valid_keys(self, key):
        assert JIRA_KEY_PATTERN.match(key)

    @pytest.mark.parametrize('key', ['Miscellaneous', 'el-123', 'EL123', 'EL-', '-123', ''])
    def test_invalid_keys(self, key):
        assert not JIRA_KEY_PATTERN.match(key)


class TestHelpers:
    def test_is_blank(self):
        assert is_blank('')
        assert is_blank('   ')
        assert is_blank(None)
        assert is_blank(float('nan'))
        assert not is_blank('EL-123')

    def test_format_duration(self):
        assert format_duration(0) == '0h 0m'
        assert format_duration(3600) == '1h 0m'
        assert format_duration(5400) == '1h 30m'
        assert format_duration(30 * 60) == '0h 30m'

    def test_truncate(self):
        assert truncate('short') == 'short'
        long_text = 'x' * 100
        assert truncate(long_text) == 'x' * 57 + '...'
        assert len(truncate(long_text)) == 60
