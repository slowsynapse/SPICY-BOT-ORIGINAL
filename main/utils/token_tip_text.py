from django.conf import settings
from main.models import SLPToken

import re
import emoji
import random

import logging
logger = logging.getLogger(__name__)

class TokenTipText(object):

    def __init__(self, *args, **kwargs):
        # supports both comma and without comma values
        self.decimal_or_whole_regex = '((((?:\d+)(\d{1,3})*([\,]\d{3})*)?(\.\d+))|((?:\d+)((\d{1,3})*([\,]\d{3})*)))'
        self.emojis_regex = self.generate_emojis_regex()
        self.token_regex = self.generate_token_regex()
        # self.token_regex = '(chili|bch|drop|honk)'  # uncomment for unit tests
        self.allowed_chars_beside = f'(\s|\,|{self.emojis_regex})?'
        self.text = kwargs.get("text", "")

    def generate_emojis_regex(self):
        emojis = SLPToken.objects.get(name='SPICE').tip_emojis
        allowed_symbols = list(emojis.keys())
        # allowed_symbols.remove('+')
        # allowed_symbols.remove('\ufe0f')
        regex = allowed_symbols[0]

        for symbol in allowed_symbols:
            if symbol != allowed_symbols[0]:
                regex += f"|{symbol}"
        return regex

    def generate_token_regex(self):
        tokens = SLPToken.objects.all()
        self.token_names = [t.name.lower() for t in tokens]
        regex = f"(\b{self.token_names[0]}\b|\b{self.token_names[0]}s\b"

        for token in self.token_names:
            if token != self.token_names[0]:
                plural = f"{token}s"
                regex+=f"|\b{token}\b|\b{plural}\b"

        return f"{regex})"

    def has_emoji(self, text):
        for char in text:
            if char in emoji.UNICODE_EMOJI or char == "+":
                return True
        return False

    def emoji_only(self, text):
        has_emoji = False
        has_others = False

        for char in text:
            if char in emoji.UNICODE_EMOJI or char == "+":
                has_emoji = True
            elif char not in emoji.UNICODE_EMOJI and char is not " ":
                has_others = True

        if has_emoji and not has_others:
            return True
        return False

    def token_generator(self):
        tokens = SLPToken.objects.all()
        potential_tokens = []
        for token in tokens:
            potential_tokens.append(token.name.lower())
            for plural_name in token.verbose_names:
                potential_tokens.append(plural_name)
        return potential_tokens

    def extract(self, **kwargs):
        text = self.text.strip(' ').lower()
        values = {}
        for token in self.token_generator():
            pattern = f'(.?(tip\s+(((?![\,])[0-9,]+(\.\d+)?)|(((?![\,])[0-9,]+)?(\.\d+)))\s+({token})))'

            results = re.findall(r"(?:^|(?<=\s))"+pattern+r"(?=\s|$)", text, flags = re.IGNORECASE)
            if results:
                for result in results:
                    word = result[0]                    
                    amount = word.split()[1]
                    amount_pattern = "^-?\d+(?:[\s,]\d{3})*(?:\.\d+)?$"
                    amount = re.findall(r"(?:^|(?<=\s))"+amount_pattern+r"(?=\s|$)", amount, flags = re.IGNORECASE)
                    if not amount: continue
                    amount = amount[0].replace(',', '')
                    amount = float(amount)
                    token = word.split()[2]
                    
                    this_token = SLPToken.objects.filter(name=token.upper())
                    if not this_token.exists(): this_token = SLPToken.objects.filter(verbose_names__icontains=token)
                    token_key = this_token.first().name
                    if token_key.upper() not in values.keys():
                        values[token_key.upper()] = 0
                    values[token_key.upper()] += amount
        return values

    def strip_allowed_chars(self, text, is_spice=False):
        allowed_chars = self.allowed_chars_beside
        allowed_chars = allowed_chars.replace('\s', ' ')
        allowed_chars = allowed_chars.replace('\,', ',')
        allowed_chars = allowed_chars.rstrip('?')
        allowed_chars = allowed_chars.rstrip(')')
        allowed_chars = allowed_chars.lstrip('(')
        allowed_chars = allowed_chars.split('|')

        for char in allowed_chars:
            text = text.lstrip(char)
            if char != ',' and not is_spice:
                text = text.rstrip(char)
        return text

    # returns the tip amount and the modified text (after calculating the amount, the tip <number> was removed)
    def get_tip_num_amount(self):
        tip_num_regex = 'tip\s+(((?![\,])[0-9,]+(\.\d+)?)|(((?![\,])[0-9,]+)?(\.\d+))))'
        tip_words = re.findall(f'(.?{tip_num_regex}.?)', self.text)
        amount = 0
        for tip_word in tip_words:
            word = tip_word[0]
            tip_num = ''
            if re.match(f'^({self.allowed_chars_beside}{tip_num_regex}{self.allowed_chars_beside})$', word):
                word = self.strip_allowed_chars(word)
                nums = word.split(',')
                tip_num = nums.pop(0)
                if re.match('^tip\s+\d{1,3}$', tip_num):
                    for num in nums:
                        if re.match('^tip\s+0+$', tip_num):
                            if re.match('^\.\d+$', num):
                                tip_num += num
                            break
                        else:
                            if re.match('^\d{3}(\.\d+)?$', num):
                                tip_num += f',{num}'
                            else:
                                break
            if tip_num != '':
                text = text.replace(tip_num, '', 1) # can be improved by removing the beside word first before calling this
                tip_num = tip_num.replace(',', '')
                amount = float(tip_num.split(' ')[-1])
                break
        return amount, text

    # returns all valid <number> spice words as an array e.g. ['200 spice', '50.5 spice', 2,000 spice]
    # def get_spice_words(self, text):
    #     tuple_spice_words = re.findall(f'(.?{self.decimal_or_whole_regex}\s+spice)', text)
    #     valid_spice_words = []
        
    #     for words in tuple_spice_words:
    #         if re.match(f'^(\s|\,|{self.emojis_regex})?{self.decimal_or_whole_regex}\s+spice$', words[0]):
    #             word = words[0].strip(' ')
    #             word = re.sub(f'(\,|{self.emojis_regex})', '', word)
    #             valid_spice_words.append(word)

    #     return valid_spice_words
    def get_num_spice_amount(self, text):
        num_spice_regex = '(((?![\,])[0-9,]+(\.\d+)?)|(((?![\,])[0-9,]+)?(\.\d+)))'
        spice_words = re.findall(f'(.?{num_spice_regex}\s+spice)', text)
        amount = 0
        for spice_word in spice_words:
            word = spice_word[0]
            num_spice = ''
            if re.match(f'^({self.allowed_chars_beside}{num_spice_regex}\s+spice)$', word):
                word = self.strip_allowed_chars(word, True)
                nums = word.split(',')
                nums.reverse()
                num_spice = nums.pop(0)
                if not re.match('^\d{3}(\.\d+)?\s+spice$', num_spice):
                    if re.match('^\s+spice$', num_spice):
                        continue
                    return float(num_spice.split(' ')[0])
                else:
                    if len(nums) == 0:
                        return float(num_spice.split(' ')[0])
                    for num in nums:
                        if re.match('^\d{1,3}$', num):
                            num_spice = f'{num}{num_spice}'
                            if re.match('^\d{1,2}$', num):
                                return float(num_spice.split(' ')[0])
                        else:
                            return float(num_spice.split(' ')[0])
                    return float(num_spice.split(' ')[0])
        return amount

    # removes all @username except for @botname
    def remove_twitter_handles(self, text):
        text = text.strip(' ')
        twitter_handles = re.findall('@\w+', text)

        for handle in twitter_handles:
            if not f'{self.bot_name}' in handle:
                text = text.replace(handle, '')

        return text

    # removes all tip <number>
    # def remove_tip_number_words(self, tip_num_arr, text):
    #     for elem in tip_num_arr:
    #         text = text.replace(elem, '')
    #     return text

# VALIDATOR FUNCTIONS
    def is_space(self, char):
        return char == ' '

    def is_emoji(self, char):
        return char in emoji.UNICODE_EMOJI or char == '+'

    # validates text format before undergoing tip computations
    def validate_text_format(self, text):
        if self.bot_name not in text:
            return False

        left_is_valid = True
        right_is_valid = True

        splitted = text.split(f'{self.bot_name}')
        try:
            left_text = splitted[0]
        except IndexError as exc:
            left_text = ''

        try:
            right_text = splitted[1]
        except IndexError as exc:
            right_text = ''

        # if both text sides are not existing, it is invalid
        if not left_text and not right_text:
            return False

        if left_text:
            # get last char of left text to identify what is beside @botname at left
            left_char_beside = left_text[-1]
            # if left beside is a space or an emoji or a '+', it is valid
            if not self.is_space(left_char_beside) and not self.is_emoji(left_char_beside):
                left_is_valid = False

        if right_text:
            # get first char of right text to identify what is beside @botname at right
            right_char_beside = right_text[0]
            # if right beside is a space it is valid
            if not self.is_space(right_char_beside):
                right_is_valid = False

        return (left_is_valid and right_is_valid)

# COMPUTATION FUNCTIONS
    # for <number> spice - gets first occurrence
    # def get_spice_amount(self, spice_word):
    #     return float(spice_word.replace(',', '').split(' ')[0])

    # for tip <number>
    # def get_tip_number_amount(self, text):
    #     return float(text.replace(',', '').split(' ')[-1])

    # for emojis in text
    def compute_emojis(self, text, opposite_text = ''):
        is_plus_only = False
        if '+' in text:
            # checks if plus is alone in text
            if re.match('^\s*([+]\s?)+\s*$', text):
                is_plus_only = True

        tip_value = 0
        emojis = SLPToken.objects.get(name='SPICE').tip_emojis.keys()
        for char in emojis:
            multiplier = 0

            if char == '+':
                if is_plus_only:
                    if opposite_text:
                        multiplier = 0
                    else:
                        multiplier = text.count(char)
                else:
                    multiplier = 0
            else:
                multiplier = text.count(char)

            if char == '\U0001F344':
                value = random.choice(range(0,1000))
                text = text.replace(char,"")
            elif char == '\u26a1\ufe0f' or char == '\u26a1':
                value = 0
                text = text.replace(char,"")
            else:
                value = emojis[char]
                if value:
                    text = text.replace(char,"")

            tip_value += (value * multiplier)
        return tip_value

    # MAIN FUNCTION FOR TWITTER/REDDIT TIP COMPUTATION
    def get_twitter_tip_amount(self, text):
        # remove all @botname except last
        botname_count = text.count(self.bot_name) - 1
        
        if botname_count <= 0:
            text = text.replace(self.bot_name, '', botname_count)
        # check first if @botname has required spaces before and after
        is_valid = self.validate_text_format(text)

        if is_valid:
            text = self.remove_twitter_handles(text).strip(' ')
            amount = 0
            # compute left amount
            amount = self.get_tip_amount(text, 'LEFT')
            # if left amount is 0, calculate right amount
            if amount == 0:
                amount += self.get_tip_amount(text, 'RIGHT')

            return amount
        else:
            return 0

    # MAIN FUNCTION FOR TELEGRAM TIP COMPUTATION
    def get_telegram_tip_amount(self, text):
        amount = 0
        orig_text = text
        
        # check if it is a trade tip
        temp_token_regex = self.token_regex.replace(')', '|spice)')
        trade_regex = f'^(trade\s+{self.decimal_or_whole_regex}\s+{temp_token_regex})$'
        if re.findall(trade_regex, text):
            return 0

        # get all tip <number>, calculate and remove in text
        amount, text = self.get_tip_num_amount(text)
        # tip_number_words = self.get_tip_number_words(text)
        # import pdb;pdb.set_trace()
        # if tip_number_words:
        #     amount += self.get_tip_number_amount(tip_number_words[0])
        #     text = self.remove_tip_number_words(tip_number_words, text)

        # amount += self.get_num_spice_amount(text)
        # get all spice words and calculate
        # spice_words = self.get_spice_words(text)
        # if spice_words:
        #     amount += self.get_spice_amount(spice_words[0])

        # compute all allowed emojis
        # if self.has_emoji(text):
            # amount += self.compute_emojis(orig_text)

        return amount

    # used only by twitter
    def get_tip_amount(self, text, direction):
        msg=''
        splitted_text = text.split(f'{self.bot_name}')
        try:
            left_text = splitted_text[0].strip(' ')
        except IndexError:
            left_text = ''
        try:
            right_text = splitted_text[1].strip(' ')
        except IndexError:
            right_text = ''

        amount = 0
        reference_text = ''
        opposite_text = ''

        if direction == 'LEFT':
            reference_text = left_text
            opposite_text = right_text
        elif direction == 'RIGHT':
            reference_text = right_text
            opposite_text = left_text

        orig_reference_text = reference_text

        if reference_text:
            # check first if is a pure tip <number>, then return <number>
            if re.match(f'^tip\s+{self.decimal_or_whole_regex}$', reference_text):
                # if there is right text, do not calculate tip
                # if right_text:
                #     return 0
                amount, reference_text = self.get_tip_num_amount(reference_text)
                return amount
            # check if it is a pure <number>, then return <number>
            if re.match(f'^{self.decimal_or_whole_regex}$', reference_text):
                return float(reference_text)
            # check if is pure emoji
            # if self.emoji_only(reference_text):
                # return self.compute_emojis(reference_text, opposite_text)

            # goes in here if left text is not pure
            # check if it has any tip <number> then calculate it, then remove

            amount, reference_text = self.get_tip_num_amount(reference_text)
            # tip_number_words = self.get_tip_number_words(reference_text)
            # if tip_number_words:
            #     amount += self.get_tip_number_amount(tip_number_words[0])
            #     reference_text = self.remove_tip_number_words(tip_number_words, reference_text)

            beside_word = ''
            # check if left beside of @botname is a number
            if direction == 'LEFT':
                beside_word = reference_text.split(' ')[-1]
            # check if right beside of @botname is a number
            elif direction == 'RIGHT':
                beside_word = reference_text.split(' ')[0]

            if re.match(f'^{self.decimal_or_whole_regex}$', beside_word):
                amount += float(beside_word.replace(',', ''))
                if amount != 0:
                    reference_text = reference_text.replace(beside_word, '', 1)

            # check if left text has any <number> spice
            amount += self.get_num_spice_amount(reference_text)

            # spice_words = self.get_spice_words(reference_text)
            # if spice_words:
            #     amount += self.get_spice_amount(spice_words[0])

            if self.has_emoji(reference_text):
                amount += self.compute_emojis(orig_reference_text, right_text)

        return amount
