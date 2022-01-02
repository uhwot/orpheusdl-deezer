from enum import Enum, auto
from utils.models import *
from utils.utils import create_temp_filename
from .dzapi import DeezerAPI


module_information = ModuleInformation(
    service_name = 'Deezer',
    module_supported_modes = ModuleModes.download | ModuleModes.lyrics | ModuleModes.covers | ModuleModes.credits,
    global_settings = {'client_id': '447462', 'client_secret': 'a83bf7f38ad2f137e444727cfc3775cf', 'bf_secret': '', 'track_url_key': ''},
    session_settings = {'email': '', 'password': ''},
    session_storage_variables = ['arl'],
    netlocation_constant = 'deezer', 
    test_url = 'https://www.deezer.com/track/3135556',
)

class ImageType(Enum):
    cover = auto(),
    artist = auto(),
    playlist = auto(),
    user = auto(),
    misc = auto(),
    talk = auto()

class ModuleInterface:
    def __init__(self, module_controller: ModuleController):
        settings = module_controller.module_settings
        self.exception = module_controller.module_error
        self.tsc = module_controller.temporary_settings_controller
        self.default_cover = module_controller.orpheus_options.default_cover_options
        self.disable_subscription_check = module_controller.orpheus_options.disable_subscription_check
        if self.default_cover.file_type is ImageFileTypeEnum.webp:
            self.default_cover.file_type = ImageFileTypeEnum.jpg

        self.session = DeezerAPI(self.exception, settings['client_id'], settings['client_secret'], settings['bf_secret'], settings['track_url_key'])
        arl = module_controller.temporary_settings_controller.read('arl')
        if arl:
            try:
                self.session.login_via_arl(arl)
            except self.exception:
                self.login(settings['email'], settings['password'])

        self.quality_parse = {
            QualityEnum.MINIMUM: 'MP3_128',
            QualityEnum.LOW: 'MP3_128',
            QualityEnum.MEDIUM: 'MP3_320',
            QualityEnum.HIGH: 'MP3_320',
            QualityEnum.LOSSLESS: 'FLAC',
            QualityEnum.HIFI: 'FLAC'
        }
        self.format = self.quality_parse[module_controller.orpheus_options.quality_tier]
        self.compression_nums = {
            CoverCompressionEnum.high: 80,
            CoverCompressionEnum.low: 50
        }
        if arl:
            self.check_sub()

    def login(self, email: str, password: str):
        arl, _ = self.session.login_via_email(email, password)
        self.tsc.set('arl', arl)
        self.check_sub()

    def get_track_info(self, track_id: str, quality_tier: QualityEnum, codec_options: CodecOptions, data={}) -> TrackInfo:
        is_user_upped = int(track_id) < 0
        format = self.quality_parse[quality_tier] if not is_user_upped else 'MP3_MISC'

        track = None
        if data and track_id in data:
            track = data[track_id]
        elif not is_user_upped:
            track = self.session.get_track(track_id)
        else:   # user-upped tracks can't be requested with deezer.pageTrack
            track = self.session.get_track_data(track_id)

        t_data = track
        if not is_user_upped:
            t_data = t_data['DATA']
        if 'FALLBACK' in t_data:
            t_data = t_data['FALLBACK']

        tags = Tags(
            album_artist = t_data['ART_NAME'],
            track_number = t_data.get('TRACK_NUMBER'),
            copyright = t_data.get('COPYRIGHT'),
            isrc = t_data['ISRC'],
            disc_number = t_data.get('DISK_NUMBER'),
            replay_gain = t_data.get('GAIN'),
            release_date = t_data.get('PHYSICAL_RELEASE_DATE')
        )

        error = None
        if not is_user_upped:
            countries = t_data['AVAILABLE_COUNTRIES']['STREAM_ADS']
            if not countries:
                error = 'Track not available'
            elif format in ('MP3_320', 'FLAC'):
                formats_360 = ['MP4_RA3', 'MP4_RA2', 'MP4_RA1']
                if quality_tier is QualityEnum.HIFI and codec_options.spatial_codecs:
                    # deezer has three different 360ra qualities, so this checks the highest quality one available
                    # if there isn't any it just gets FLAC instead
                    for f in formats_360:
                        if self.session.check_format(t_data['MD5_ORIGIN'], f, t_data['SNG_ID'], t_data['MEDIA_VERSION']):
                            format = f
                            break
                
                if format not in formats_360:
                    if self.session.country not in countries:
                        error = 'Track not available in your country, try downloading in 128/360RA instead'
                    elif format not in self.session.available_formats:
                        error = 'Format not available by your subscription'
                    elif t_data[f'FILESIZE_{format}'] == '0':
                        error = 'Format not available'
                

        codec = {
            'MP3_MISC': CodecEnum.MP3,
            'MP3_128': CodecEnum.MP3,
            'MP3_320': CodecEnum.MP3,
            'FLAC': CodecEnum.FLAC,
            'MP4_RA1': CodecEnum.MHA1,
            'MP4_RA2': CodecEnum.MHA1,
            'MP4_RA3': CodecEnum.MHA1,
        }[format]

        bitrate = {
            'MP3_MISC': None,
            'MP3_128': 128,
            'MP3_320': 320,
            'FLAC': 1411,
            'MP4_RA1': None,
            'MP4_RA2': None,
            'MP4_RA3': None,
        }[format]

        download_extra_kwargs = {
            'id': t_data['SNG_ID'],
            'track_token': t_data['TRACK_TOKEN'],
            'track_token_expiry': t_data['TRACK_TOKEN_EXPIRE'],
            'format': format,
            'md5_origin': t_data['MD5_ORIGIN'],
            'media_version': t_data['MEDIA_VERSION']
        }

        return TrackInfo(
            name = t_data['SNG_TITLE'] if not t_data.get('VERSION') else f'{t_data["SNG_TITLE"]} {t_data["VERSION"]}',
            album_id = t_data['ALB_ID'],
            album = t_data['ALB_TITLE'],
            artists = [a['ART_NAME'] for a in t_data['ARTISTS']] if 'ARTISTS' in t_data else [t_data['ART_NAME']],
            tags = tags,
            codec = codec,
            cover_url = self.get_image_url(t_data['ALB_PICTURE'], ImageType.cover, ImageFileTypeEnum.jpg, self.default_cover.resolution, self.compression_nums[self.default_cover.compression]),
            release_year = t_data['PHYSICAL_RELEASE_DATE'].split('-')[0] if 'PHYSICAL_RELEASE_DATE' in t_data else None,
            explicit = t_data['EXPLICIT_LYRICS'] == '1' if 'EXPLICIT_LYRICS' in t_data else None,
            artist_id = t_data['ART_ID'],
            bit_depth = 24 if codec is CodecEnum.MHA1 else 16,
            sample_rate = 48 if codec is CodecEnum.MHA1 else 44.1,
            bitrate = bitrate,
            download_extra_kwargs = download_extra_kwargs,
            cover_extra_kwargs = {'data': {track_id: t_data['ALB_PICTURE']}},
            credits_extra_kwargs = {'data': {track_id: t_data.get('SNG_CONTRIBUTORS')}},
            lyrics_extra_kwargs = {'data': {track_id: track.get('LYRICS')}},
            error = error
        )

    def get_track_download(self, id, track_token, track_token_expiry, format, md5_origin, media_version):
        path = create_temp_filename()

        # legacy urls don't have country restrictions, but aren't available for 320 and flac
        # you can still get shit like 360RA with those though. bruh moment
        if format in ('MP3_320', 'FLAC'):
            url = self.session.get_track_url(id, track_token, track_token_expiry, format)
        else:
            url = self.session.get_legacy_track_url(md5_origin, format, id, media_version)

        self.session.dl_track(id, url, path)

        return TrackDownloadInfo(
            download_type = DownloadEnum.TEMP_FILE_PATH,
            temp_file_path = path
        )

    def get_album_info(self, album_id: str, data={}) -> Optional[AlbumInfo]:
        album = data[album_id] if album_id in data else self.session.get_album(album_id)
        a_data = album['DATA']

        # placeholder images can't be requested as pngs
        cover_type = self.default_cover.file_type if a_data['ALB_PICTURE'] != '' else ImageFileTypeEnum.jpg

        return AlbumInfo(
            name = a_data['ALB_TITLE'],
            artist = a_data['ART_NAME'],
            tracks = [track['SNG_ID'] for track in album['SONGS']['data']],
            release_year = a_data['PHYSICAL_RELEASE_DATE'].split('-')[0],
            explicit = a_data['EXPLICIT_ALBUM_CONTENT']['EXPLICIT_LYRICS_STATUS'] in (1, 4),
            artist_id = a_data['ART_ID'],
            cover_url = self.get_image_url(a_data['ALB_PICTURE'], ImageType.cover, cover_type, self.default_cover.resolution, self.compression_nums[self.default_cover.compression]),
            cover_type = cover_type,
            all_track_cover_jpg_url = self.get_image_url(a_data['ALB_PICTURE'], ImageType.cover, ImageFileTypeEnum.jpg, self.default_cover.resolution, self.compression_nums[self.default_cover.compression]),
        )

    def get_playlist_info(self, playlist_id: str, data={}) -> PlaylistInfo:
        playlist = data[playlist_id] if playlist_id in data else self.session.get_playlist(playlist_id, -1, 0)
        p_data = playlist['DATA']

        # placeholder images can't be requested as pngs
        cover_type = self.default_cover.file_type if p_data['PLAYLIST_PICTURE'] != '' else ImageFileTypeEnum.jpg

        user_upped_dict = {}
        for t in playlist['SONGS']['data']:
            if t['SNG_ID'] < 0:
                user_upped_dict[t['SNG_ID']] = t

        return PlaylistInfo(
            name = p_data['TITLE'],
            creator = p_data['PARENT_USERNAME'],
            tracks = [t['SNG_ID'] for t in playlist['SONGS']['data']],
            release_year = p_data['DATE_ADD'].split('-')[0],
            creator_id = p_data['PARENT_USER_ID'],
            cover_url = self.get_image_url(p_data['PLAYLIST_PICTURE'], ImageType.playlist, cover_type, self.default_cover.resolution, self.compression_nums[self.default_cover.compression]),
            cover_type = cover_type,
            description = p_data['DESCRIPTION'],
            track_extra_kwargs = {'data': user_upped_dict}
        )

    def get_artist_info(self, artist_id: str, get_credited_albums: bool, artist_name = None) -> ArtistInfo:
        name = artist_name if artist_name else self.session.get_artist_name(artist_id)

        return ArtistInfo(
            name = name,
            albums = self.session.get_artist_album_ids(artist_id, 0, -1, get_credited_albums),
        )

    def get_track_credits(self, track_id: str, data={}):
        if int(track_id) < 0:
            return []

        credits = data[track_id] if track_id in data else self.session.get_track_contributors(track_id)
        if not credits:
            return []
        return [CreditsInfo(k, v) for k, v in credits.items()]

    def get_track_cover(self, track_id: str, cover_options: CoverOptions, data={}) -> CoverInfo:
        cover_md5 = data[track_id] if track_id in data else self.session.get_track_cover(track_id)

        if cover_options.file_type is ImageFileTypeEnum.webp:
            cover_options.file_type = ImageFileTypeEnum.jpg
        url = self.get_image_url(cover_md5, ImageType.cover, cover_options.file_type, cover_options.resolution, self.compression_nums[cover_options.compression])
        return CoverInfo(url=url, file_type=cover_options.file_type)

    def get_track_lyrics(self, track_id: str, data={}) -> LyricsInfo:
        if int(track_id) < 0:
            return LyricsInfo()

        try:
            lyrics = data[track_id] if track_id in data else self.session.get_track_lyrics(track_id)
        except self.exception:
            return LyricsInfo()
        if not lyrics:
            return LyricsInfo()

        synced_text = None
        if 'LYRICS_SYNC_JSON' in lyrics:
            synced_text = ''
            for line in lyrics['LYRICS_SYNC_JSON']:
                if 'lrc_timestamp' in line:
                    synced_text += f'{line["lrc_timestamp"]}{line["line"]}\n'
                else:
                    synced_text += '\n'

        return LyricsInfo(embedded=lyrics['LYRICS_TEXT'], synced=synced_text)

    def search(self, query_type: DownloadTypeEnum, query: str, track_info: TrackInfo = None, limit: int = 10):
        results = {}
        if track_info and track_info.tags.isrc:
            results = [self.session.get_track_data_by_isrc(track_info.tags.isrc)]
        if not results:
            results = self.session.search(query, query_type.name, 0, limit)['data']

        if query_type is DownloadTypeEnum.track:
            return [SearchResult(
                    result_id = i['SNG_ID'],
                    name = i['SNG_TITLE'] if not i.get('VERSION') else f'{i["SNG_TITLE"]} {i["VERSION"]}',
                    artists = [a['ART_NAME'] for a in i['ARTISTS']],
                    explicit = i['EXPLICIT_LYRICS'] == '1',
                    additional = [i["ALB_TITLE"]]
                ) for i in results]
        elif query_type is DownloadTypeEnum.album:
            return [SearchResult(
                    result_id = i['ALB_ID'],
                    name = i['ALB_TITLE'],
                    artists = [a['ART_NAME'] for a in i['ARTISTS']],
                    year = i['PHYSICAL_RELEASE_DATE'].split('-')[0],
                    explicit = i['EXPLICIT_ALBUM_CONTENT']['EXPLICIT_LYRICS_STATUS'] in (1, 4),
                    additional = [i["NUMBER_TRACK"]]
                ) for i in results]
        elif query_type is DownloadTypeEnum.artist:
            return [SearchResult(
                    result_id = i['ART_ID'],
                    name = i['ART_NAME'],
                    extra_kwargs = {'artist_name': i['ART_NAME']}
                ) for i in results]
        elif query_type is DownloadTypeEnum.playlist:
            return [SearchResult(
                    result_id = i['PLAYLIST_ID'],
                    name = i['TITLE'],
                    artists = [i['PARENT_USERNAME']],
                    additional = [i["NB_SONG"]]
                ) for i in results]

    def get_image_url(self, md5, img_type: ImageType, file_type: ImageFileTypeEnum, res, compression):
        filename = {
            ImageFileTypeEnum.jpg: f'{res}x{res}-000000-{compression}-0-0.jpg',
            ImageFileTypeEnum.png: f'{res}x{res}-none-100-0-0.png'
        }[file_type]

        return f'https://cdns-images.dzcdn.net/images/{img_type.name}/{md5}/{filename}'
    
    def check_sub(self):
        if not self.disable_subscription_check and (self.format not in self.session.available_formats):
            print('Deezer: quality set in the settings is not accessible by the current subscription')
