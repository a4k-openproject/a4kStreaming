<img align="left" width="115px" height="115px" src="icon.png">

# a4kStreaming

<br/>

## Status
[![Kodi version](https://img.shields.io/badge/kodi%20versions-18--20-blue)](https://kodi.tv/) ![status-api](https://github.com/a4k-openproject/a4kStreaming/workflows/API/badge.svg) ![status-suite](https://github.com/a4k-openproject/a4kStreaming/workflows/Suite/badge.svg)

## Description

IMDb-based media browser addon for KODI with streaming support via external providers.
<br/>
Designed for low-end devices and Estuary skin.

## Preview
![usage](https://media.giphy.com/media/IdUqHVT9dxgZ5YEObr/source.gif)

## Features
  * IMDb:
    * Authentication via cookie
    * Browsing for titles
      * Trending
      * Fan Favourites
      * Recommended
      * Discover by Year
    * Browsing Shows
      * Seasons
      * Season episodes
    * Lists
    * Watchlist
    * Search for titles or people
    * Debrid files/transfers browsing
    * Auto mark as watched when played more than 90 percents
    * Contextmenu
      * Cast and Crew browsing
      * Trailers
      * Mark as watched/unwatched (by rating/unrating a title)
      * Add/Remove to/from list
      * Rate/Unrate titles
      * Seeing similar titles (i.e. More like this)
      * Add new sources to debrid cache
  * Provider support
    * Install
    * Manage
    * Auto update
    * Caching of results
  * Debrid support
    * Premiumize
    * RealDebrid
    * AllDebrid
  * Misc
    * Migrate watched titles from Trakt.tv to IMDb (via rating)
    * Migrate movies and shows collection from Trakt.tv to IMDb custom lists

## Installation

Steps to install a4kStreaming:
1. Go to the KODI **File manager**.
2. Click on **Add source**.
3. The path for the source is https://a4k-openproject.github.io/a4kStreaming/packages/
4. (Optional) Name it **a4kStreaming-repo**.
5. Head to **Addons**.
6. Select **Install from zip file**.
7. When it asks for the location select **a4kStreaming-repo** and install `a4kStreaming-repository.zip`.
8. Go back to **Addons** and select **Install from repository**
9. Select the **a4kStreaming** menu item

## Rich meta browsing (more artwork, fanart, etc)

For rich meta browsing the recommended approach is to use [TheMovieDb Helper](https://kodi.tv/addon/plugins-video-add-ons/themoviedb-helper).
<br/>
Then install [http://bit.ly/a4kStreaming-tmdb](http://bit.ly/a4kStreaming-tmdb) in order to use **a4kStreaming** as a player.

## Trakt Scrobbling

For Trakt scrobbling support it is recommended to use [Trakt](https://kodi.tv/addon/program-add-ons-scripts/trakt).
<br/>
The addon will detect when a video is being played by **a4kStreaming** and update it in [Trakt.tv](https://trakt.tv)

## IMDb Authentication

The IMDb authentication token is the value of a cookie named `at-main`.
</br>
It can be obtained by opening [imdb.com](https://www.imdb.com) in a browser, log in, then get it from:
* (Chrome/Edge) DevTools > Application > Cookies
* (Safari/Firefox) DevTools > Storage > Cookies

## Contribution

Configure hooks for auto update of `addons.xml`:
```sh
git config core.hooksPath .githooks
```
## License

MIT
