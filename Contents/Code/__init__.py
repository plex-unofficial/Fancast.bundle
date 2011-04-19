######
# Imports
from PMS import *
from Support import *
import re
import os
import random
######

######
# Globals
######
# Plugin Settings
FANCAST_PREFIX     = "/video/fancast"
######
# Fancast URLS
FANCAST_URL                     = "http://www.fancast.com"
FANCAST_TV_WIDGET    = "http://www.fancast.com/full_episodes_fragment.widget"
FANCAST_MOVIES_WIDGET           = "http://www.fancast.com/movies_fragment.widget"
FANCAST_TRAILERS_URL            = "http://www.fancast.com/trailers"
######
# Excluded Content
# Content from selected providers cannot be played via the plugin
# This is due to it being served from a 3rd party using MoveNetworks
HIDE_ABC                        = True # At the moment we can't work with the Move Networks player on abc.com so we need to hide the shows
HIDE_CW                         = True # Hide 'The CW' for the same reason as ABC
HIDE_PROTECTED_PROVIDERS        = True # Some movies are supplied by 'Protected Providers' (i.e. not free) eg Starz, exlucde them
######
# Cache Intervals
CACHE_FRONTPAGE                 = 3600   # The length of time to cache the front page, used for Top5
CACHE_SHOWLIST                  = 18000  # The length of time to cache the list of available shows
CACHE_SHOWMETADATA              = 2419200# The length of time to cache the metadata for show (photo and network) - 4 weeks
CACHE_SHOWASSETS                = 18000  # The length of time to cache the availalbe assets for a show
CACHE_ASSETMETADATA             = 2419200# The length of time to cache the metadata for an individual asset - 4 weeks
METADATE_UPDATE_PROBABILITY     = 0.02   # The probability that an update for existing show metadata will be attempted, this should update all assets over a week, after the original cache has expired
######
# Debug Flags
DEBUG                           = False # General logging
DEBUG_METADATA_FETCH            = False # Log metadata fetch activities
DEBUG_XML_RESPONSE              = False # Log the response to PMS
######


#####
# Notes on terminology
#
# Fancast consist of multiple 'shows'
# A show can be either a TV Series or a Movie
# The identifier used by the plugin is taken from the url eg
# /tv/South-Park/62926/ or /movies/The-Taking-of-Pelham-1%2C-2%2C-3/22089/ etc..
# The metadata once retrieved is stored in the plugin dictionary at show-id ie show-/tv/South-Park/62926/
# Metadata for shows is:

# A show consists of multiple assets, i.e. episodes, clips or the movie itself


def Start():

  # Plugin Initialization

  Plugin.AddPrefixHandler(FANCAST_PREFIX, MainMenu, L('fancast'), "icon-default.png", "art-default.png")
  Plugin.AddViewGroup("Details", viewMode="InfoList", mediaType="items")
  Plugin.AddViewGroup("List", viewMode="List", mediaType="items")

  MediaContainer.title1 = L('fancast')
  MediaContainer.content = 'Items'
  MediaContainer.viewGroup = 'List'
  MediaContainer.art = R('art-default.png')

###########################
# Caching and metadata update functions
#

def UpdateCache():

  # Updates the metadata dictionary for shows
  # This must run at least once before the plugin is available
  # Show metadata is stored in the plugin dictionary once retrieved
  # The user facing plugin functions pull from the dictionary and thus do not refresh the cache directly

  # We retrieve metadata for tv, movies and trailers

  for url in ( FANCAST_TV_WIDGET, FANCAST_MOVIES_WIDGET, FANCAST_TRAILERS_URL):
    page = XML.ElementFromURL(url, isHTML=True, cacheTime=CACHE_SHOWLIST)
    if url == FANCAST_TRAILERS_URL:
      shows = page.xpath("//div[@id='episodeList']/ul[@class='fullEpisodeList']/li[not(@class='head')]")
    else:
      if HIDE_PROTECTED_PROVIDERS:
        shows = page.xpath("//div[@class='fullEpisodeList']//div/ul/li[not(starts-with(@class, 'protected'))]")
      else:
        shows = page.xpath("//div[@class='fullEpisodeList']//div/ul/li")

    # Build a list of availalbe show id's
    showIds = []
    for show in shows:
        showFullUrl = show.xpath(".//a")[0].get('href') # //a here as the link can be within a 'new episode' div
        showId = re.search('^(.*/(?:movies|tv)/[^/]+/\d+/)', showFullUrl).group(1)
        showIds.append(showId)

    GetShowMetadata(showIds)

  # Once UpdateCache has run at least once we note this in the dictionary, users can now access the plugin
  Dict.Set('cacheRanOnce', True)

def GetShowMetadata(showIds):

  # Grabs metadata for shows and updates the dictionary
  # showIds is a list of ids
  # If we already have metadata then we roll the die to decide if we will refresh or not

  # This should only be called from UpdateCache

  # Check we actually have some showIds and return if not
  if len (showIds) == 0:
    return False

  # To efficienty retrieve metadata from the site we perform parallel requests

  @parallelize
  def GetShows():
    for id in showIds:
      if not Dict.HasKey('show-'+id) or ( random.random() < METADATE_UPDATE_PROBABILITY ):
        @task
        def GetShow(showId = id):

          # Start with clean metadata each time
          showMeta = {};

          if DEBUG_METADATA_FETCH:
            PMS.Log("Fetching Metadata for show: %s" % showId)

          # We use the 'photos' page of the show to retrieve both a photo and the associated network
          photoPageUrl = FANCAST_URL + showId + "photos"
          page = XML.ElementFromURL(photoPageUrl, isHTML=True, cacheTime=CACHE_SHOWMETADATA)

          # Find the show title from the page
          title = TidyString(page.xpath("//div[@id='pageHeadline']//span[@class='title']")[0].text)
          showMeta['title'] = title

          # Find the show's photos
          images = page.xpath("//div[@id='listHolder']/ul[@id='viewTable']/li/a/img")
          imageUrlLarge = ''
          if len(images) > 0:
            imageElement = images[0]
            imageUrlSmall = imageElement.get('src') # src is already fully qualified
            # Zoom up to a decent size (this assumes all images are avaialble in all sizes
            imageUrlLarge = re.sub('121_87', '640_320', imageUrlSmall)
            showMeta['thumb'] = imageUrlLarge
          else:
            showMeta['thumb'] = ''

          if DEBUG_METADATA_FETCH:
            PMS.Log("Thumb for %s set to %s" % (showId, showMeta['thumb']))

          # Find the show's network - Not all shows display a network
          networkLinks = page.xpath("//div[@id='swoosh']/a")
          if len(networkLinks) > 0:
            networkLink = networkLinks[0].get('href')
            networkName = re.search(r'\/tv-networks\/([^\/]+)\/', networkLink).group(1)
            showMeta['network'] = networkName
          else:
            showMeta['network'] = ''

          if DEBUG_METADATA_FETCH:
            PMS.Log("Network for %s set to %s" % (showId, showMeta['network']))

          # Store the metadata into the dictionary
          key = "show-"+showId
          if DEBUG_METADATA_FETCH:
            PMS.Log( "Adding to dictionary with key: %s" % key)
          Dict.Set(key, showMeta)


def GetAssetMetadata(assetIds):

  # Grabs metadata for individual assets
  # This is used when a page has show id's but lacks sufficient metadata about the shows for a nice presentation to the user

  # Pass a list of assetIds to grab metadata for

  @parallelize
  def FetchAssets():
    for id in assetIds:
      if not Dict.HasKey('asset-'+id) or ( random.random() < METADATE_UPDATE_PROBABILITY ):
        @task
        def FetchAsset(assetId = id):

          # Start with clean metadata each time
          assetMeta = {}

          if DEBUG_METADATA_FETCH:
            PMS.Log("Fetching Metadata for asset: %s" % assetId)

          # The metadata is stored within the javascript on the video's page (video.playerData)
          # So fetch the page as a string and grep out the bit we want
          assetPageUrl = FANCAST_URL + assetId + '/videos'
          page = HTTP.Request(assetPageUrl, cacheTime=CACHE_ASSETMETADATA)

          # Extract the value of video.playerData and parse as XML
          assetMetadataString = re.search (r'video.playerData = "(.*</entity>)', page).group(1)
          assetMetadata = XML.ElementFromString(assetMetadataString, isHTML=False)

          # Gather available metadata
          showTitle = assetMetadata.xpath("//metadata/entityName")[0].text
          episodeTitle = assetMetadata.xpath("//metadata/videoTitle")[0].text
          thumb = assetMetadata.xpath("//entity/imageUrl")[0].text
          description = assetMetadata.xpath("//metadata/description")[0].text
          duration = ConvertDuration( assetMetadata.xpath("//metadata/duration")[0].text )
          airdate = assetMetadata.xpath("//metadata/airDate")[0].text
          season = assetMetadata.xpath("//metadata/season")[0].text
          episodeNumber = assetMetadata.xpath("//metadata/episode")[0].text

          if not season:
            season = 'Unknown'
          if not episodeNumber:
            episodeNumber = 'Unknown'

          assetMeta['showTitle'] = showTitle
          assetMeta['episodeTitle'] = episodeTitle
          assetMeta['thumb'] = thumb
          assetMeta['description'] = description
          assetMeta['duration'] = duration
          assetMeta['airdate'] = airdate
          assetMeta['season'] = season
          assetMeta['episodeNumber'] = episodeNumber
          assetMeta['url'] = FANCAST_URL + assetId + '/videos'

          # Store metadata into the dictionary
          key = 'asset-' + assetId
          if DEBUG_METADATA_FETCH:
            PMS.Log( "Adding to dictionary with key: %s" % key)
          Dict.Set(key, assetMeta)

#######################
# Plugin menus

def MainMenu():

  # Top level menu
  # First ensure the cache has been updated at least once, if not ask the user to come back later #TODO check wording

  if Dict.Get('cacheRanOnce') == True:

    # Dispaly the avaialble categories of content and TODO 'search'
    dir = MediaContainer()

    dir.Append(Function(DirectoryItem(TVMovieMainMenu, title=L('tv'), thumb=R('icon-default.png')), mediaType='tv'))
    dir.Append(Function(DirectoryItem(TVMovieMainMenu, title=L('movies'), thumb=R('icon-default.png')), mediaType='movies'))
#    dir.Append(Function(DirectoryItem(TrailerBrowser, title=L('trailers'), thumb=R('icon-default.png'))))
#    dir.Append(Function(DirectoryItem(ClipBrowser, title=L('clips'), thumb=R('icon-default.png'))))

    if DEBUG_XML_RESPONSE:
      PMS.Log(dir.Content())
    return dir

  else:
    return (MessageContainer(header=L('fancast'), message=L('noinitialcache'), title1=L('fancast')))

def TVMovieMainMenu(sender, mediaType):

  # Display the top level menu for TV and Movies
  # They are very similar so we use the same function, just adding new episodes, and network as options to 'tv'

  dir = MediaContainer()
  dir.title2 = L(mediaType)

  dir.Append(Function(DirectoryItem(TVMovieBrowser, title=L('all'), thumb=R('icon-default.png')), mediaType=mediaType, filterType='all'))
  dir.Append(Function(DirectoryItem(Top5Browser, title=L('top5'), thumb=R('icon-default.png')), mediaType=mediaType))
  dir.Append(Function(DirectoryItem(TVMovieFilterSelector, title=L('filterGenre'), thumb=R('icon-default.png')), mediaType=mediaType, filterType='genre'))

  # Only TV episodes can be filtered by Network or have New Episodes
  if mediaType == 'tv':
    dir.Append(Function(DirectoryItem(TVMovieFilterSelector, title=L('filterNetwork'), thumb=R('icon-default.png')), mediaType=mediaType, filterType='network'))
    dir.Append(Function(DirectoryItem(TVMovieBrowser, title=L('newEpisodes'), thumb=R('icon-default.png')), mediaType=mediaType, filterType='new', filterName=L('newEpisodes')))

  if DEBUG_XML_RESPONSE:
    PMS.Log(dir.Content())
  return dir


def TVMovieFilterSelector(sender, mediaType, filterType):

  # Present a list of available 'filers' i.e. Genres or Networks

  # mediatype is 'tv' or 'movies'
  # filterType is 'genere' or 'network' (tv only)

  dir = MediaContainer()
  dir.title1 = L(mediaType)
  dir.title2 = L(filterType)

  # Pull down the appropriate 'widget', this lists available filters

  if mediaType == 'tv':
    url = FANCAST_TV_WIDGET
  else:
    url = FANCAST_MOVIES_WIDGET

  page = XML.ElementFromURL(url, isHTML=True, cacheTime=CACHE_SHOWLIST)

  if ( filterType == 'network' ):
    availableFilters = page.xpath("//div[@id='filters']/div[@class='FilterbyNetwork']/ul/li[not(@class='selected')]")
  else:
     availableFilters = page.xpath("//div[@id='filters']/div[@class='FilterbyGenre']/ul/li[not(@class='selected')]")

  for filter in availableFilters:
    filterOnClick = filter.xpath("./a")[0].get('onclick')
    # Strip away the javascript function call (filterEpList)
    filterUrl = FANCAST_URL + re.search(r"'([^']+)'", filterOnClick).group(1)
    filterName = str(filter.xpath("./a/text()")[0])

    # Hide ABC and CW networks, append all the others
    if filterName != 'ABC' or HIDE_ABC == False:
      if filterName != 'CW' or HIDE_CW == False:
        dir.Append(Function(DirectoryItem(TVMovieBrowser, title=filterName, summary=L('filterGenre'), subtitle='', thumb=R('icon-default.png')), mediaType=mediaType, filterType=filterType, filterUrl=filterUrl, filterName=filterName))

  if DEBUG_XML_RESPONSE:
    PMS.Log(dir.Content())
  return dir


def TVMovieBrowser(sender, mediaType, filterType=None, filterUrl=None, filterName=None):

  # Display a list of shows filtered by various options

  # mediaType is tv / movies
  # filterType is all / top5 / genre / network / new
  # filterValue is the selected value, eg Fox / Comedy etc.. 
  # filterName is the human redable name of the filter

  # We have either a filterUrl or we're showing 'all'

  if DEBUG:
    PMS.Log ("Filter type %s name %s" % (filterType, filterName))

  if filterUrl == None:
    if mediaType == 'tv':
      filterUrl = FANCAST_TV_WIDGET
    else:
      filterUrl = FANCAST_MOVIES_WIDGET

  dir = MediaContainer()
  # TODO title1?
  dir.title2 = filterName
  dir.viewGroup = 'List'

  if DEBUG:
    PMS.Log("Fetching filtered page: %s" % filterUrl)

  # Get the filtered results and show the avaialble shows
  page = XML.ElementFromURL(filterUrl, isHTML=True, cacheTime=CACHE_SHOWLIST)

  if filterType=='new':
    # New episodes are within a 'new episode' div
    shows = page.xpath("//div[@class='fullEpisodeList']//div/ul/li/div")
  else:
    if HIDE_PROTECTED_PROVIDERS:
      shows = page.xpath("//div[@class='fullEpisodeList']//div/ul/li[not(starts-with(@class, 'protected'))]")
    else:
      shows = page.xpath("//div[@class='fullEpisodeList']//div/ul/li")



  if DEBUG:
    PMS.Log ("Found %d shows" % len(shows))

  for show in shows:
    showFullUrl = show.xpath(".//a")[0].get('href') # //a here as the link can be within a 'new episode' div
    showId = re.search('^(.*/(?:movies|tv)/[^/]+/\d+/)', showFullUrl).group(1)
    showKey = 'show-'+showId

    # Check that we have a metadata key for this show, if not just ignore it and it will be picked up in the next cache update
    if (Dict.HasKey(showKey)):

      # Grab existing metadata
      showMeta = Dict.Get(showKey)
      title = showMeta['title']
      thumb = showMeta['thumb']
      network = showMeta['network']

      # Set the default thumbnail if none is found
      if thumb == '':
        thumb = R('icon-default.png')

      # Hide ABC and CW networks, append all the others
      if not (network.find('ABC-Entertainment') >= 0) or HIDE_ABC == False:
        if not (network.find('CW-Television-Network') >= 0) or HIDE_CW == False:
          if mediaType == 'tv':
            dir.Append(Function(DirectoryItem(ShowBrowserTV, title=title, summary='', subitle='', thumb=thumb), showId=showId, showName=title))
          else:
            dir.Append(Function(DirectoryItem(ShowBrowserMovies, title=title, summary='', subitle='', thumb=thumb), showId=showId, showName=title))
    else:
      if DEBUG:
        PMS.Log ("No show metadata was found for %s" % showId)

  if DEBUG_XML_RESPONSE:
    PMS.Log(dir.Content())
  return dir


def TrailerBrowser(sender):
  # TODO this!
  pass

def ClipBrowser(sender):
  #TODO this!
  pass

def ShowBrowserTV(sender, showId, showName, selectedSeasonId=None, selectedSeasonName=None):

  # List available assets for selected tv show

  dir = MediaContainer()
  dir.title2 = showName

  page = XML.ElementFromURL(FANCAST_URL + showId + 'full-episodes', isHTML=True, cacheTime=CACHE_SHOWASSETS)

  # TV shows can have multiple seasons
  # If more that one season is available the list the available seasons and have the user select one

  seasonsExist = False
  seasons = page.xpath("//div[@id='listHolder']/ul[1]/li[@class='seasonsMenu']/select[@name='seasons']/option[not(@value='all')]")

  if len(seasons) > 1:
    # More that one season exists
    seasonsExist = True

  if seasonsExist and not selectedSeasonId:
    # More that one season exist but the user has not yet selected one
    # Present a list of available seasons

    for season in seasons:

      seasonId = season.get('value');
      if DEBUG: 
        PMS.Log("Found season %s" % seasonId)

      seasonName = re.search('^\s*(\S.*\S)\s*$', season.xpath("./text()")[0]).group(1)

      # Find a thumbnail for the season - this is the thumbanil for the first listed episode in the season
      thumb = page.xpath("//div[@id='" + seasonId + "']//td[@class='first']/a/img")[0].get('src')

      dir.Append(Function(DirectoryItem(ShowBrowserTV, title=seasonName, thumb=thumb), showId=showId, showName=showName, selectedSeasonId=seasonId, selectedSeasonName=seasonName))

  else:

    # Either there are no seaons, or the user has now selected one

    dir.viewGroup = 'Details'

    if selectedSeasonId:
      assets = page.xpath("//div[@id='" + selectedSeasonId + "']/table[@class='videoList fourColumn']//tr[not(@class='newEpHeader')]")
    else:
      assets = page.xpath("//div[@id='listHolder']//tr[not(@class='newEpHeader')]")

    for asset in assets:
      thumb = asset.xpath(".//img")[0].get('src')
      title = TidyString(asset.xpath("./td[position()=1]/a[position()=2]")[0].text)
      summary = asset.xpath(".//p")[0].text
      episodeId = TidyString(asset.xpath("./td[@class='two']")[0].text)
      episodeId = re.sub (r'S', 'Season ', episodeId)
      episodeId = re.sub (r'Ep', 'Episode ', episodeId)
      # FIXME - This pipe is not being removed for some reason
      episodeId = re.sub (r'|', r'', episodeId)
      episodeId = re.sub (r'Unknown', 'Season: Unknown', episodeId)
      airDate= TidyString(asset.xpath("./td[@class='three']")[0].text)
      subtitle= episodeId + "\n" + "Airdate: " + airDate
      duration = asset.xpath("./td[@class='first']//span")[0].text
      duration = re.search ( r'([^)]+)', duration).group(1)
      url = FANCAST_URL + asset.xpath("./td[@class='first']/a[position()=1]")[0].get('href')

      duration = ConvertDuration(duration)

      dir.Append(Function(WebVideoItem(PlayVideo, title=title, subtitle=subtitle, summary=summary, duration=duration, thumb=thumb), url=str(url)))

  if DEBUG_XML_RESPONSE:
    PMS.Log(dir.Content())
  return dir


def ShowBrowserMovies(sender, showId, showName):

  # Show movie 

  dir = MediaContainer()
  dir.title2 = showName
  dir.viewGroup = 'Details'

  # We get metadata from 2 sources the main listings page and the 'about' page

  listingsPage = XML.ElementFromURL(FANCAST_URL + showId + 'full-movie', isHTML=True, cacheTime=CACHE_SHOWASSETS)
  aboutPage = XML.ElementFromURL(FANCAST_URL + showId + 'about', isHTML=True, cacheTime=CACHE_SHOWASSETS)

  # Get metadata from listingsPage
  title = TidyString(listingsPage.xpath("//table[@class='videoList twoColumn']//td[@class='first']/a[2]")[0].text)
  PMS.Log("title %s" % title)
  url = FANCAST_URL + listingsPage.xpath("//table[@class='videoList twoColumn']//td[@class='first']/a")[0].get('href')
  duration = listingsPage.xpath("//table[@class='videoList twoColumn']//td[@class='first']/a/span")[0].text
  duration = ConvertDuration(re.search ( r'([^)]+)', duration).group(1))
  yearAndRating = TidyString(listingsPage.xpath("//div[@id='pageHeadline']//span[@class='meta']")[0].text)
  # Strip the brackets surrounding the year
  yearAndRating = re.sub (r'\(([^\(]+)\)', r'\1', yearAndRating)
  
  # Get metadata from about page
  summary = aboutPage.xpath("//div[@id='leftcontent']/div[@class='clearfix']/p")[0].text
  thumb = R('icon-default.png')
  try:
    thumb = aboutPage.xpath("//div[@id='thumbNail']//img")[0].get('src')
  except:
    pass

  dir.Append(Function(WebVideoItem(PlayVideo, title=title, subtitle=yearAndRating, summary=summary, duration=duration, thumb=thumb), url=str(url)))

  if DEBUG_XML_RESPONSE:
    PMS.Log(dir.Content())
  return dir





      

def Top5Browser(sender, mediaType):

  # Shows the top 5 tv / movies or trailers

  dir = MediaContainer()
  dir.title1 = L(mediaType)
  dir.title2 = L('top5')
  dir.viewGroup = 'Details'

  page = XML.ElementFromURL(FANCAST_URL, isHTML= True, cacheTime=CACHE_FRONTPAGE)

  if mediaType == 'tv':
    divId = 'playlistTabBody0'
  elif mediaType == 'movies':
    divId = 'playlistTabBody1'
  else:
    # Trailers
    divId = 'playlistTabBody2'

  items = page.xpath("//div[@id='" + divId + "']/ol/li")

  # The available metadata is very sparse so we grab the asset id's then search for their metadata

  assetIds = []

  for item in items:

    itemUrl = item.xpath("./a")[0].get('href')
    assetId = re.search (r'http://www.fancast.com(.*)/videos', itemUrl).group(1)

    assetIds.append(assetId)

  GetAssetMetadata(assetIds)

  for assetId in assetIds:

    assetMetadata = Dict.Get('asset-'+assetId)
    title = assetMetadata['showTitle'] + ' : ' + assetMetadata['episodeTitle']
    subtitle = assetMetadata['season'] + " | " + assetMetadata['episodeNumber']
    description = assetMetadata['description']
    duration = assetMetadata['duration']
    thumb = assetMetadata['thumb']
    url = assetMetadata['url']

    dir.Append(Function(WebVideoItem(PlayVideo, title=title, subtitle=subtitle, summary=description, duration=duration, thumb=thumb), url=url))

  if DEBUG_XML_RESPONSE:
    PMS.Log(dir.Content())
  return dir



    

def PlayVideo(sender, url):

  # First clear any existing comfancastbookmarks.sol files
  # This prevents the 'resume from where you left off' dialog from showing
  os.system("/bin/rm ~/Library/Preferences/Macromedia/Flash\ Player/#SharedObjects/*/www.fancast.com/static-*/swf/FCVidContainerInit.swf/comfancastbookmarks.sol")

  # Request to play the video at URL, rewrite the URL so it puls in the correct site config

  metadata = XML.ElementFromURL(url, isHTML=True, cacheTime=CACHE_ASSETMETADATA, errors='ignore')

  # Determine aspect ratio

  width = metadata.xpath("//meta[@name='video_width']")[0].get('content')
  width = re.sub (r',', r'', width)
  width = re.sub (r'"', r'', width)

  height = metadata.xpath("//meta[@name='video_height']")[0].get('content')
  height = re.sub (r',', r'', height)
  height = re.sub (r'"', r'', height)

  if DEBUG:
    PMS.Log("width %s height %s" % (width, height))


  if float(height) == 0:
    # For some reason we didn't get a 'height' let's make one up
    height = 360
    width = 640

  ratio = float(width) / float(height)

  # 1.55 is the cut off ratio used by Fancast
  if ratio < 1.55:
    # Player is 4x3
    aspect = '4x3'

  elif ratio < 2.2:
    # Player is 16x9
    aspect = '16x9'

  else:
    # Player is 2.35:1 (eg Watchmen HD Trailer)
    aspect = '2.35x1'
  url = url + "#" + aspect

  if DEBUG:
    PMS.Log("Redirecting to base "+url)

  if Plugin.LastPrefix: prefix = Plugin.LastPrefix
  else: prefix = Plugin.Prefixes()[0]
  webkitUrl = "plex://localhost/video/:/webkit?url=%s&prefix=%s" % (String.Quote(url, usePlus=True), prefix)

  if DEBUG:
    PMS.Log("Redirecting to webkit url" + webkitUrl)

  return Redirect(webkitUrl)




