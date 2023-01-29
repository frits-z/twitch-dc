import datetime
import logging
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import time
from typing import Optional, Union, List, Callable


logger = logging.getLogger(__name__)


def datetime_to_str(dt: datetime.datetime) -> str:
    return dt.astimezone().isoformat() if dt is not None else None


class HelixAPI:
    """A connection to the Twitch Helix API."""

    BASE_URL = "https://api.twitch.tv/helix/"
    TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    _ratelimit_reset_timestamp = '0'
    _ratelimit_remaining = 0

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: Optional[str] = None,
        access_token_refresh_callback: Optional[Callable[[], str]] = None,
    ):
        """Twitch Helix API.

        Args:
            client_id: x
            client_secret: x
            access_token: x
            access_token_refresh_callback: x

        docs: https://dev.twitch.tv/docs/api/
        """
        self.client_id = client_id
        self.client_secret = client_secret

        self.access_token_refresh_callback = access_token_refresh_callback
        
        # _access_token_refreshed is used to avoid getting stuck in a loop if access token is refreshed
        # but request response is again UNAUTHORIZED
        self._access_token_refreshed = False

        if access_token is None:
            self._refresh_access_token()
        else:
            self.access_token = access_token

        self.headers = {'Client-ID': self.client_id, 'Authorization': f'Bearer {self.access_token}'}
        self.http = self._setup_http_client()


    def _setup_http_client(self) -> requests.Session:
        """ Create persistent requests session that automatically retries on specific request fails

        Retries on:
        - Status Codes 5XX: Server error
        - Requests Exceptions (like Timeout or Connection)

        Waits an increasing amount of time between each retry.
        
        source: https://findwork.dev/blog/advanced-usage-python-requests-timeouts-retries-hooks/ 
        """
        retry_strategy = Retry(
            total = 5,
            status_forcelist=[500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            backoff_factor=1
            )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        http = requests.Session()
        http.mount("https://", adapter)
        http.mount("http://", adapter)
        logger.debug("Created HTTP session")
        return http


    def _wait_for_rate_limit_reset(self) -> None:
        if self._ratelimit_remaining != 0:
            raise Exception("Request returned 429 but rate limit is not 0...?")
        logger.debug("Waiting for rate limit reset")
        current_time = time.time()
        reset_time = int(self._ratelimit_reset_timestamp)
        wait_time = 0.1 + reset_time - current_time
        if wait_time > 0:
            time.sleep(wait_time)


    def _refresh_access_token(self) -> None:
        """ Twitch OAuth get new access token

        Uses OAuth client credentials flow (server-to-server API requests)
        docs: https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#oauth-client-credentials-flow 
        """
        post_data = {'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials'}
        response = self.http.post(HelixAPI.TOKEN_URL, data=post_data, timeout=2)
        response.raise_for_status
        response_data = response.json()
        self.access_token = response_data['access_token']
        self.headers['Authorization'] = f"Bearer {self.access_token}"
        if self.access_token_refresh_callback:
            self.access_token_refresh_callback(self.access_token)
        self._access_token_refreshed = True
        logger.debug("Refreshed app access token")


    def _get_request(
        self,
        endpoint: str,
        params: dict,
    ) -> dict:
        """Send a single request and return response data.
        
        Parameters
        ----------
        endpoint
            Path of the resource after the API Base URL
        params
            Query parameters


        Any dictionary key whose value is None will not be added to the URLs query string by Requests.

        Rate limits, timeouts, connection, and server errors are dealt with in the http session setup.
        Reauthorization is triggered in this function
        """
        logger.debug("_get_request: endpoint = %s, params = %s", endpoint, params)

        response = self.http.get(f"{HelixAPI.BASE_URL}{endpoint}", params=params, headers=self.headers)
        self._ratelimit_remaining = response.headers.get("Ratelimit-Remaining")
        self._ratelimit_reset_timestamp = response.headers.get("Ratelimit-Reset")

        if response.status_code == requests.codes.OK: #200:
            self._refresh_access_token = False
            return response.json()

        elif response.status_code == requests.codes.TOO_MANY_REQUESTS: #429
            self._wait_for_rate_limit_reset()
            return self._get_request(endpoint, params=params)

        elif response.status_code == requests.codes.UNAUTHORIZED: #401
            logger.warning("_get_request: request unauthorized, app access token may be expired")

            if self._access_token_refreshed:
                logger.error("New access token doesn't resolve unauthorized status code")
                raise Exception
            
            self._refresh_access_token()
            return self._get_request(endpoint, params=params)

        else:
            logger.error(
                "Cannot handle request to: %s, params: %s, with status code: %s %s",
                endpoint, params, response.status_code, response.reason)
            raise Exception


    def _paginated_request(
        self,
        endpoint: str,
        params: dict,
        max_records_per_page: int,
        cap_records: Optional[int] = None,
    ) -> List[dict]:
        """Send paginated (multiple) requests and return response data. 
        
        Args:
            endpoint: Helix API endpoint
            params: Payload
            max_records_per_page: Maximum objects the API can return per page for this method
            cap_records: How many total objects would we like to retrieve
                Does not necessarily get served, as the API may cap this.
                Defaults to None, meaning no cap.

        Returns:
            A list of dict where each dict is a record (e.g. a clip)


        Docs: https://dev.twitch.tv/docs/api/guide#pagination
        """
        responses_data = []

        if cap_records is None:
            records_to_go = max_records_per_page
        else:
            records_to_go = cap_records

        while records_to_go > 0 or cap_records is None:
            params['first'] = min(max_records_per_page, records_to_go)
            response = self._get_request(endpoint, params)
            responses_data.extend(response['data'])

            records_to_go -= len(response['data'])

            try:
                _cursor = response['pagination']['cursor']
                params['after'] = _cursor
            except:
                #TEMP
                print("No cursor found, reached the end. Break out of loop.")
                break

        logger.debug(f"Completed paginated request for {endpoint}, {params}")
        return responses_data

    #Bits resource
    def get_cheermotes(
        self
    ):
        raise NotImplementedError

    #Channels resource
    def get_channel_information(
        self
    ):
        raise NotImplementedError


    def get_channel_emotes(
        self
    ):
        raise NotImplementedError

    #Chat resource
    def get_global_emotes(
        self
    ):
        raise NotImplementedError


    def get_emote_sets(
        self
    ):
        raise NotImplementedError


    def get_channel_chat_badges(
        self
    ):
        raise NotImplementedError


    def get_global_chat_badges(
        self
    ):
        raise NotImplementedError


    def get_chat_settings(
        self
    ):
        raise NotImplementedError


    def get_user_chat_color(
        self
    ):
        raise NotImplementedError


    #Clips resource
    def get_clips(
        self,
        broadcaster_id: Optional[str] = None,
        game_id: Optional[str] = None,
        clip_id: Optional[List[str]] = None,
        started_at : Optional[datetime.datetime] = None,
        ended_at : Optional[datetime.datetime] = None,
        cap_records: Optional[int] = None,
    ) -> List[dict]:
        """ Get clips

        Args:
            broadcaster_id: #TODO
            game_id: x
            clip_id: x
            started_at: x
            ended_at: x
            cap_records: Set a cap to the maximum number of records to return.
                May not be honored by the API (i.e. less are returned).

        Returns:
            A list of dicts, where every dict is a clip.

        Raises:
            ValueError: Not exactly one of clip_id, broadcaster_id, or game_id is passed
            ValueError: More than 100 clip_ids are queried.
        """
        if clip_id is not None and len(clip_id) > 100:
            raise ValueError("A maximum of 100 clips can be queried in one call")
        if not (sum([clip_id is not None, broadcaster_id is not None, game_id is not None]) == 1):
            raise ValueError("The clip_id, broadcaster_id, and game_id parameters are mutually exclusive.")
        params = {
            'broadcaster_id': broadcaster_id,
            'game_id': game_id,
            'id': clip_id,
            'started_at': datetime_to_str(started_at),
            'ended_at': datetime_to_str(ended_at),
        }
        return self._paginated_request(
            endpoint='clips',
            params=params,
            max_records_per_page=100,
            cap_records=cap_records)


    #Games resource
    def get_top_games(
        self,
        cap_records: Optional[int] = None 
    ) -> List[dict]:
        """ Get top games

        #TODO
        """
        params = {}
        return self._paginated_request(
            endpoint='games/top',
            params=params,
            max_records_per_page=100,
            cap_records=cap_records
        )
        

    def get_games(
        self,
        game_ids: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        igdb_ids: Optional[List[str]] = None
    ):
        """ Get games
        
        #TODO
        """
        if game_ids is None and names is None and igdb_ids is None:
            raise ValueError("You have to specify a list of game IDs, names, or both.")
        if ((len(game_ids) if game_ids is not None else 0)
            + (len(names) if names is not None else 0)
            + (len(igdb_ids) if igdb_ids is not None else 0)
            ) > 100:
            raise ValueError("The sum total of the number of games you may look up is 100.")
        params = {
            'id': game_ids,
            'name': names,
            'igdb_id': igdb_ids
        }
        return self._get_request(
            endpoint='games',
            params=params
        )


    #Schedule resource
    def get_channel_stream_schedule(
        self
    ):
        raise NotImplementedError


    def get_get_channel_icalendar(
        self
    ):
        raise NotImplementedError


    #Search resource
    def search_categories(
        self
    ):
        raise NotImplementedError


    def search_channels(
        self
    ):
        raise NotImplementedError


    #Music resource
    def get_soundtrack_current_track(
        self
    ):
        raise NotImplementedError


    def get_soundtrack_playlist(
        self
    ):
        raise NotImplementedError


    def get_soundtrack_playlists(
        self
    ):
        raise NotImplementedError


    #Streams resrouce
    def get_streams(
        self
    ):
        raise NotImplementedError


    #Tags resource
    def get_all_stream_tags(
        self
    ):
        raise NotImplementedError


    def get_stream_tags(
        self
    ):
        raise NotImplementedError


    #Teams resource
    def get_channel_teams(
        self
    ):
        raise NotImplementedError


    def get_teams(
        self
    ):
        raise NotImplementedError


    #Users resource
    def get_users(
        self,
        user_ids: Optional[List[str]] = None,
        logins: Optional[List[str]] = None,
    ) -> List[dict]:
        """ Get users

        Args: 
            user_ids: User IDs
            logins: Login names.

        Returns:
            List of dict (users)


        Raises:
            x #TODO
        
        """
        if user_ids is None and logins is None:
            raise ValueError("You have to specify a list of user IDs, login names, or both.")
        if not(isinstance(user_ids, list) or user_ids is None):
            raise TypeError("user_ids has to be a list or None")
        if not(isinstance(logins, list) or logins is None):
            raise TypeError("logins has to be a list or None")        
        if (len(user_ids) if user_ids is not None else 0) + (len(logins) if logins is not None else 0) > 100:
            raise ValueError("The sum total of the number of users you may look up is 100.")
        params = {
            'id': user_ids,
            'logins': logins
        }
        return self._get_request(endpoint='users', params=params)['data']


    def get_users_follows(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str]= None,
        cap_records: Optional[int] = None,
    ):
        """ Get users follows

        Args:
            from_id:
            to_id: 
            cap_records: Set a cap to the maximum number of records to return.
                May not be honored by the API (i.e. less are returned). 
                If all you need is total follower count, highly recommend 
                capping this to 1 to avoid sending umpteen requests.
                
        Raises:
            x #TODO
        """
        if from_id is None and to_id is None:
            raise ValueError("You must specify from_id, to_id, or both.")
        max_records_per_page = 100
        params = {
            'from_id': from_id,
            'to_id': to_id,
            'first': 1
        }            
        # Structure of response body for user/follows is rather unique.
        # Contains a total field and 'regular' list of dict (like other endpoints).
        # We don't need to accomodate if the request is for less than max_records_per_page
        # If we want more records, we have to do an initial request to grab the total field
        # and then do paginated requests for the data field.
        if (cap_records if cap_records is not None else 1) > max_records_per_page:
            params['first'] = cap_records
            return self._get_request(endpoint='users/follows', params=params)
        full_response = {}
        initial_response = self._get_request(endpoint='users/follows', params=params)
        full_response['total'] = initial_response['total']
        full_response['data'] = self._paginated_request(
            endpoint='user/follows',
            params=params,
            max_records_per_page=max_records_per_page,
            cap_records=cap_records
        )
        return full_response
        

    def get_user_active_extensions(
        self
    ):
        raise NotImplementedError


    #Videos resource
    def get_videos(
        self,
        video_ids: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        game_id: Optional[str] = None,
        language: Optional[str] = None,
        period: Optional[str] = None,
        sort: Optional[str] = None,
        video_type: Optional[str] = None,
        cap_records: Optional[int] = None,
    ) -> List[dict]:
        """ Get videos

        Args:
            id: A list of IDs that identify the videos you want to get
            user_id: The ID of the user whose list of videos you want to get.
            game_id: A category or game ID
            language: Filter by the language that the video owner broadcasts in. 
                ISO 639-1 two-letter code for German (i.e., DE). 
                If the language is not supported, use “other.”
            period: Filter videos by when they were published.
                Valid: 'all', 'day', 'month', 'week'.
                Default is 'all'.
            sort: Sort returned videos.
                Valid: 'time', 'trending', 'views'.
                Default is 'time'.
            video_type: Filter video's type. Case-sensitive.
                Valid: 'all', 'archive', 'highlight', 'upload'.
                Default is 'all'.
            cap_records: Set a cap to the maximum number of records to return.
                May not be honored by the API (i.e. less are returned).

        Returns:
            A list of dicts, where every dict is a video.

        Raises:
            ValueError: #TODO

        """
        if video_ids is not None and len(video_ids) > 100:
            raise ValueError("A maximum of 100 video IDs can be queried in one call")
        if not (sum([video_ids is not None, user_id is not None, game_id is not None]) == 1):
            raise ValueError("The id, user_id, and game_id parameters are mutually exclusive.")
        if language is not None and game_id is None:
            raise ValueError("Specify language only if you specify the game_id query parameter.")
        if period is not None and (game_id is None and user_id is None):
            raise ValueError("Specify period only if you specify the game_id or user_id query parameter.")
        if sort is not None and (game_id is None and user_id is None):
            raise ValueError("Specify sort only if you specify the game_id or user_id query parameter.")
        if video_type is not None and (game_id is None and user_id is None):
            raise ValueError("Specify video_type only if you specify the game_id or user_id query parameter.")
        if cap_records is not None and (game_id is None and user_id is None):
            raise ValueError("Specify cap_records only if you specify the game_id or user_id query parameter.")
        params = {
            'id': video_ids,
            'user_id': user_id,
            'game_id': game_id,
            'language': language,
            'period': period,
            'sort': sort,
            'type': video_type
        }

        if video_ids is not None:
            return self._get_request(endpoint='videos', params=params)['data']
        else:
            return self._paginated_request(
                endpoint='videos',
                params=params,
                max_records_per_page=100,
                cap_records=cap_records)