from lyriclens.domain import lrc


def test_lrc_rounding_multiline_and_empty_passages():
    assert lrc([
        dict(start=59.999, end=65, text='First\nSecond'),
        dict(start=65, end=66, text='  \n'),
        dict(start=3600.125, end=3602, text='Final'),
    ]) == '[01:00.00]First\n[01:00.00]Second\n[60:00.12]Final\n'
    assert lrc([]) == ''
