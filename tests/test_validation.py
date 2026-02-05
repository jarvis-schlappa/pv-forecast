"""Tests für pvforecast.validation."""

from datetime import date

import pytest

from pvforecast.validation import (
    ValidationError,
    parse_date_string,
    validate_csv_files,
    validate_date,
    validate_date_range,
    validate_latitude,
    validate_longitude,
    validate_path_exists,
    validate_path_readable,
    validate_path_writable,
    validate_positive_float,
    validate_positive_int,
)


class TestValidateLatitude:
    """Tests für validate_latitude."""

    def test_valid_latitude(self):
        assert validate_latitude(0) == 0.0
        assert validate_latitude(51.83) == 51.83
        assert validate_latitude(-90) == -90.0
        assert validate_latitude(90) == 90.0

    def test_invalid_latitude_too_low(self):
        with pytest.raises(ValidationError) as exc:
            validate_latitude(-91)
        assert "-90" in str(exc.value)

    def test_invalid_latitude_too_high(self):
        with pytest.raises(ValidationError) as exc:
            validate_latitude(91)
        assert "90" in str(exc.value)

    def test_invalid_latitude_type(self):
        with pytest.raises(ValidationError) as exc:
            validate_latitude("51.83")  # type: ignore
        assert "Zahl" in str(exc.value)


class TestValidateLongitude:
    """Tests für validate_longitude."""

    def test_valid_longitude(self):
        assert validate_longitude(0) == 0.0
        assert validate_longitude(7.28) == 7.28
        assert validate_longitude(-180) == -180.0
        assert validate_longitude(180) == 180.0

    def test_invalid_longitude_too_low(self):
        with pytest.raises(ValidationError) as exc:
            validate_longitude(-181)
        assert "-180" in str(exc.value)

    def test_invalid_longitude_too_high(self):
        with pytest.raises(ValidationError) as exc:
            validate_longitude(181)
        assert "180" in str(exc.value)


class TestValidatePathExists:
    """Tests für validate_path_exists."""

    def test_existing_path(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        result = validate_path_exists(test_file)
        assert result == test_file

    def test_non_existing_path(self, tmp_path):
        with pytest.raises(ValidationError) as exc:
            validate_path_exists(tmp_path / "nonexistent.txt")
        assert "nicht gefunden" in str(exc.value)

    def test_custom_description(self, tmp_path):
        with pytest.raises(ValidationError) as exc:
            validate_path_exists(tmp_path / "missing.csv", "CSV-Datei")
        assert "CSV-Datei" in str(exc.value)


class TestValidatePathReadable:
    """Tests für validate_path_readable."""

    def test_readable_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        result = validate_path_readable(test_file)
        assert result == test_file

    def test_non_existing_file(self, tmp_path):
        with pytest.raises(ValidationError):
            validate_path_readable(tmp_path / "nonexistent.txt")


class TestValidatePathWritable:
    """Tests für validate_path_writable."""

    def test_writable_existing_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        result = validate_path_writable(test_file)
        assert result == test_file

    def test_writable_new_file_in_existing_dir(self, tmp_path):
        new_file = tmp_path / "new.txt"
        result = validate_path_writable(new_file)
        assert result == new_file

    def test_writable_new_file_in_new_dir(self, tmp_path):
        new_file = tmp_path / "subdir" / "new.txt"
        result = validate_path_writable(new_file)
        assert result == new_file
        # Verzeichnis sollte erstellt worden sein
        assert new_file.parent.exists()


class TestParseDateString:
    """Tests für parse_date_string."""

    def test_iso_format(self):
        assert parse_date_string("2024-06-15") == date(2024, 6, 15)

    def test_german_format(self):
        assert parse_date_string("15.06.2024") == date(2024, 6, 15)

    def test_german_short_format(self):
        assert parse_date_string("15.06.24") == date(2024, 6, 15)

    def test_invalid_format(self):
        with pytest.raises(ValidationError) as exc:
            parse_date_string("2024/06/15")
        assert "Ungültiges" in str(exc.value)
        assert "YYYY-MM-DD" in str(exc.value)

    def test_invalid_date(self):
        with pytest.raises(ValidationError):
            parse_date_string("2024-13-01")  # Ungültiger Monat

    def test_whitespace_stripped(self):
        assert parse_date_string("  2024-06-15  ") == date(2024, 6, 15)


class TestValidateDate:
    """Tests für validate_date."""

    def test_date_object(self):
        d = date(2024, 6, 15)
        assert validate_date(d) == d

    def test_string_date(self):
        assert validate_date("2024-06-15") == date(2024, 6, 15)

    def test_min_date_constraint(self):
        with pytest.raises(ValidationError) as exc:
            validate_date("2020-01-01", min_date=date(2024, 1, 1))
        assert "Minimum" in str(exc.value)

    def test_max_date_constraint(self):
        with pytest.raises(ValidationError) as exc:
            validate_date("2030-01-01", max_date=date(2025, 12, 31))
        assert "Maximum" in str(exc.value)

    def test_custom_description(self):
        with pytest.raises(ValidationError) as exc:
            validate_date("invalid", description="Startdatum")
        assert "Startdatum" in str(exc.value)


class TestValidateDateRange:
    """Tests für validate_date_range."""

    def test_valid_range(self):
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)
        assert validate_date_range(start, end) == (start, end)

    def test_same_date(self):
        d = date(2024, 6, 15)
        assert validate_date_range(d, d) == (d, d)

    def test_invalid_range(self):
        with pytest.raises(ValidationError) as exc:
            validate_date_range(date(2024, 12, 31), date(2024, 1, 1))
        assert "liegt nach" in str(exc.value)


class TestValidatePositiveInt:
    """Tests für validate_positive_int."""

    def test_valid_positive_int(self):
        assert validate_positive_int(1) == 1
        assert validate_positive_int(100) == 100

    def test_zero(self):
        with pytest.raises(ValidationError) as exc:
            validate_positive_int(0)
        assert "positiv" in str(exc.value)

    def test_negative(self):
        with pytest.raises(ValidationError):
            validate_positive_int(-1)

    def test_float(self):
        with pytest.raises(ValidationError) as exc:
            validate_positive_int(1.5)  # type: ignore
        assert "Ganzzahl" in str(exc.value)

    def test_bool_rejected(self):
        # bool ist technisch ein int-Subtyp, sollte aber abgelehnt werden
        with pytest.raises(ValidationError):
            validate_positive_int(True)  # type: ignore


class TestValidatePositiveFloat:
    """Tests für validate_positive_float."""

    def test_valid_positive_float(self):
        assert validate_positive_float(1.5) == 1.5
        assert validate_positive_float(9.92) == 9.92

    def test_int_accepted(self):
        assert validate_positive_float(10) == 10.0

    def test_zero(self):
        with pytest.raises(ValidationError):
            validate_positive_float(0)

    def test_negative(self):
        with pytest.raises(ValidationError):
            validate_positive_float(-1.5)


class TestValidateCsvFiles:
    """Tests für validate_csv_files."""

    def test_valid_csv_files(self, tmp_path):
        csv1 = tmp_path / "file1.csv"
        csv2 = tmp_path / "file2.csv"
        csv1.write_text("header\ndata")
        csv2.write_text("header\ndata")

        result = validate_csv_files([csv1, csv2])
        assert len(result) == 2
        assert result[0] == csv1
        assert result[1] == csv2

    def test_empty_list(self):
        with pytest.raises(ValidationError) as exc:
            validate_csv_files([])
        assert "Keine CSV-Dateien" in str(exc.value)

    def test_non_existing_file(self, tmp_path):
        with pytest.raises(ValidationError) as exc:
            validate_csv_files([tmp_path / "missing.csv"])
        assert "nicht gefunden" in str(exc.value)

    def test_wrong_extension(self, tmp_path):
        txt_file = tmp_path / "data.txt"
        txt_file.write_text("content")

        with pytest.raises(ValidationError) as exc:
            validate_csv_files([txt_file])
        assert "keine CSV-Datei" in str(exc.value)

    def test_accepts_strings(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("header\ndata")

        # String statt Path sollte akzeptiert werden
        result = validate_csv_files([str(csv_file)])
        assert len(result) == 1
