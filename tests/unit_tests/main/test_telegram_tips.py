import mock
import pytest
from pytest_mock import mocker


@pytest.mark.parametrize(
    'text, options', [
        # TEST CASES FOR HAM TIPPING
        ("📡",{"ham": 1 }),
        ("🎙️",{"ham":5 }),
        ("🎧",{"ham": 10 }), 
        ("💰",{"ham": 0.00000001 }),
        ("🎤",{"ham": 25 }),
        ("🆘",{"ham": 50 }),
        ("🎁",{"ham": 100}),

        # TEST CASES FOR ZAPT TIPPING
        # TEST CASES FOR RNEW TIPPING
        # TEST CASES FOR MIST TIPPING
        # TEST CASES FOR BCH TIPPING
        # TEST CASES FOR DROP TIPPING
        # TEST CASES FOR HONK TIPPING

        # TEST CASES FOR SPICE TIPPING
        ("+", {"spice": 5}),
        ("👍", {"spice": 5}), 
        ("🔥", {"spice": 10}), 
        ("🍕", {"spice": 50}), 
        ("💋", {"spice": 75}), 
        ("🌶️", {"spice": 25}), 
        ("🍷", {"spice": 100}), 
        ("🍪", {"spice": 500}), 
        ("🥂", {"spice": 600}), 
        ("💎", {"spice": 1000}), 
        ("🍼",{"spice": 0.00000001}), 
        ("🍄", {"spice": "undefined"}), 

        # TEST CASES FOR EMOJI TIPPING COMBINATION
        ("🍼 📡",{"spice": 0.00000001, "ham": 1}), 

        # TEST CASES FOR TEXT TIPPING COMBINATION
        ("🍼 tip 10 ham",{"spice": 0.00000001, "ham": 10}), 

    ]
)

@pytest.mark.django_db
def test_regex_pattern(mocker, text, options):
    from main.models import SLPToken
    from main.utils.token_tip_emoji import TokenTipEmoji
    from main.utils.token_tip_text import TokenTipText
    
    token_tip_emoji_calc = TokenTipEmoji(text=text)
    token_tip_text_calc = TokenTipText(text=text)

    has_tips = token_tip_emoji_calc.extract()
    has_text_tips = token_tip_text_calc.extract()

    for key in has_text_tips.keys(): has_tips[key] = has_text_tips[key]
    
    if not has_tips: assert options == {}
    
    for token in has_tips.keys():    
        value = has_tips[token]
        expected_value = options.get(token.lower(), 0)
        if expected_value == "undefined": expected_value = float(value)
        assert value == expected_value