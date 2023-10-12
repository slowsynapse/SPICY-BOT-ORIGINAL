import re
import logging
logger = logging.getLogger(__name__)

class Misc_Pattern(object):

	def check_lightning(self, text):
		logger.info('Lightning')
		#is_ln_only = False	
		msg = ''

		if '\u26a1\ufe0f' in text or '\u26a1' in text:
			# if re.match('^\s*([\u26a1\ufe0f|\u26a1]\s?)+\s*$', text):
			# 	is_ln_only = True
			#if is_ln_only:
			#ln_total = text.count('\u26a1\ufe0f')
			ln_total = text.count('\u26a1')
			msg = 'Please try again in %s months' % (ln_total*18)				

			logger.info('msg: %s', msg)
		return msg