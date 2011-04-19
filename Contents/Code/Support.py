# Support functions for Fancast plugin
import re

def ConvertDuration(durationString):
  # Takes hh:mm:ss or mm:ss and returns a plex duration (ms)

  if re.search(r':', durationString):
    durationParts = re.search(r'((\d*):)?(\d+):(\d+)', durationString)
    if durationParts.group(2) is not None:
      # Time has hours minutes and seconds
      durationSeconds = (int(durationParts.group(2)) * 3600 )+ ( int(durationParts.group(3)) * 60 ) +  int(durationParts.group(4))
    else:
      # Time has just minutes and seconds
      durationSeconds = int(durationParts.group(3)) * 60  +  int(durationParts.group(4))
  else:
      durationSeconds = int(durationString)
  
  return  str(durationSeconds * 1000)


def TidyString(stringToTidy):
  # Function to tidy up strings works ok with unicode, 'strip' seems to have issues in some cases so we use a regex
  if stringToTidy:
    # Strip new lines
    stringToTidy = re.sub(r'\n', r' ', stringToTidy)
    # Strip leading / trailing spaces
    stringSearch = re.search(r'^\s*(\S.*?\S?)\s*$', stringToTidy)
    if stringSearch == None:
      return ''
    else:
      return stringSearch.group(1)
  else:
    return ''

