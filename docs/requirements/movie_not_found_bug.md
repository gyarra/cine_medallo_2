
# Fix Bug 'NO ME SIGAS' not found

When running cineprox_download, one movie was not found that should have been found:

```
INFO 2026-01-26 21:31:05,657 cineprox_download_task Starting cineprox_download_task
INFO 2026-01-26 21:31:06,821 download_utilities Scraping page: https://www.cineprox.com/cartelera/medellin/florida
INFO 2026-01-26 21:31:18,479 cineprox_download_task Found 55 movies, 13 active (excluding 'pronto')
INFO 2026-01-26 21:31:19,290 download_utilities Scraping page: https://www.cineprox.com/detalle-pelicula/1981-no-me-sigas
INFO 2026-01-26 21:31:25,289 movie_lookup_service Searching TMDB for: 'NO ME SIGAS' (listing name: 'NO ME SIGAS')
INFO 2026-01-26 21:31:26,296 tmdb_service Searching TMDB for movie: 'NO ME SIGAS' (language=es-ES)
INFO 2026-01-26 21:31:27,161 tmdb_service Fetching TMDB movie details for ID: 81255 (language=es-ES, credits=True, videos=False)
INFO 2026-01-26 21:31:27,856 tmdb_service Fetching TMDB movie details for ID: 512200 (language=es-ES, credits=True, videos=False)
INFO 2026-01-26 21:31:28,651 tmdb_service Fetching TMDB movie details for ID: 851644 (language=es-ES, credits=True, videos=False)
INFO 2026-01-26 21:31:29,362 tmdb_service Fetching TMDB movie details for ID: 50546 (language=es-ES, credits=True, videos=False)
INFO 2026-01-26 21:31:30,152 tmdb_service Fetching TMDB movie details for ID: 83899 (language=es-ES, credits=True, videos=False)
WARNING 2026-01-26 21:31:30,561 movie_lookup_service No suitable TMDB match found for 'NO ME SIGAS'
```

### Print more info in the logs
When a movie is not found, we should print in the logs
a. All of the extracted metadata
b. The data passed into TMDB API - in fact we should *always* print this, on every request to TMDB
c. The full json response from TMDB API
Update the code to print this information in the logs

### Search our existing database before searching TMDB.com
The movie already existed in our database.
It's in the movie table with ID 43
We should actually see if there is a matching movie in our Database already before checking TMDB API
Update the code to check in the database before checking TMDB.
Add 2 automated tests for this


### Why didn't we get a match?
Can you figure out why we didn't get a match in