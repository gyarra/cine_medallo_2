from django.http import HttpResponse

from movies_app.models import Movie, Showtime, Theater


def theater_list(request):
    """Return a list of all active theaters."""
    theaters = Theater.objects.filter(is_active=True).order_by("city", "name")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Theaters - Cine Medallo</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f5f5f5; }
            .banner { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 24px 40px; margin-bottom: 24px; }
            .banner h1 { margin: 0; font-size: 32px; }
            .banner .subtitle { color: #aaa; margin-top: 4px; }
            .banner nav { margin-top: 16px; }
            .banner nav a { color: #f5c518; text-decoration: none; margin-right: 24px; font-weight: 500; }
            .banner nav a:hover { text-decoration: underline; }
            .content { padding: 0 40px 40px 40px; }
            h2 { color: #333; margin-top: 0; }
            .city-header { margin-top: 32px; color: #555; font-size: 20px; border-bottom: 2px solid #ddd; padding-bottom: 8px; }
            .city-header:first-child { margin-top: 0; }
            .theaters-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 16px; margin-top: 16px; }
            .theater { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .theater h3 { margin: 0 0 8px 0; font-size: 18px; }
            .theater h3 a { color: #0066cc; text-decoration: none; }
            .theater h3 a:hover { text-decoration: underline; }
            .chain { color: #888; font-size: 13px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
            .address { color: #444; font-size: 14px; }
            .details { color: #666; font-size: 13px; margin-top: 8px; }
            .details a { color: #0066cc; }
        </style>
    </head>
    <body>
        <div class="banner">
            <h1>🎬 Cine Medallo</h1>
            <div class="subtitle">Movie showtimes in Medellín</div>
            <nav>
                <a href="/">Movies</a>
                <a href="/theaters/">Theaters Near You</a>
            </nav>
        </div>
        <div class="content">
            <h2>Theaters Near You (""" + str(theaters.count()) + """)</h2>
    """

    current_city = None
    for t in theaters:
        if t.city != current_city:
            if current_city is not None:
                html += "</div>"
            current_city = t.city
            html += f'<h3 class="city-header">{t.city}</h3><div class="theaters-grid">'

        html += f"""
        <div class="theater">
            <h3><a href="/theaters/{t.slug}/">{t.name}</a></h3>
            <div class="chain">{t.chain}</div>
            <div class="address">{t.address}</div>
            <div class="details">
                {t.neighborhood}
                {f' · {t.screen_count} screens' if t.screen_count else ''}
                {f' · <a href="{t.website}" target="_blank">Website</a>' if t.website else ''}
            </div>
        </div>
        """

    html += "</div></div></body></html>"
    return HttpResponse(html)


def theater_detail(request, slug):
    """Return details for a single theater by slug."""
    from datetime import date as date_class

    try:
        t = Theater.objects.get(slug=slug, is_active=True)
    except Theater.DoesNotExist:
        return HttpResponse("<h1>Theater not found</h1>", status=404)

    # Get today's showtimes for this theater
    today = date_class.today()
    showtimes = (
        Showtime.objects.filter(theater=t, start_date=today)
        .select_related("movie")
        .order_by("movie__title_es", "start_time")
    )

    # Group showtimes by movie
    showtimes_by_movie: dict[int, dict] = {}
    for st in showtimes:
        movie_id = st.movie.id  # pyright: ignore[reportAttributeAccessIssue]
        if movie_id not in showtimes_by_movie:
            showtimes_by_movie[movie_id] = {
                "movie": st.movie,
                "times": [],
            }
        showtimes_by_movie[movie_id]["times"].append(st)

    today_str = today.strftime("%A, %B %d, %Y")
    showtimes_html = ""
    if showtimes_by_movie:
        showtimes_html += f'<h3 class="date-header">{today_str}</h3>'
        for movie_data in showtimes_by_movie.values():
            movie = movie_data["movie"]
            times = movie_data["times"]
            times_list = []
            for st in times:
                time_str = st.start_time.strftime("%I:%M %p").lstrip("0")
                format_str = f' <span class="format">({st.format})</span>' if st.format else ""
                times_list.append(f'<span class="time">{time_str}{format_str}</span>')

            poster_html = f'<img class="movie-poster" src="{movie.poster_url}" alt="{movie.title_es}">' if movie.poster_url else '<div class="movie-poster-placeholder">🎬</div>'
            showtimes_html += f'''
            <div class="movie-showtimes">
                <a href="/movies/{movie.slug}/" class="movie-link">
                    {poster_html}
                </a>
                <div class="movie-details">
                    <div class="movie-title"><a href="/movies/{movie.slug}/">{movie.title_es}</a></div>
                    <div class="times">{" ".join(times_list)}</div>
                </div>
            </div>
            '''
    else:
        showtimes_html = '<p class="no-showtimes">No showtimes available for today</p>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{t.name} - Cine Medallo</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f5f5f5; }}
            .banner {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 24px 40px; margin-bottom: 24px; }}
            .banner h1 {{ margin: 0; font-size: 32px; }}
            .banner .subtitle {{ color: #aaa; margin-top: 4px; }}
            .banner nav {{ margin-top: 16px; }}
            .banner nav a {{ color: #f5c518; text-decoration: none; margin-right: 24px; font-weight: 500; }}
            .banner nav a:hover {{ text-decoration: underline; }}
            .container {{ max-width: 900px; margin: 0 auto; padding: 0 40px 40px 40px; }}
            .theater-card {{ background: white; padding: 32px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .theater-card h2 {{ margin: 0 0 8px 0; color: #333; }}
            .chain {{ color: #888; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 24px; }}
            .info {{ margin-bottom: 12px; color: #444; }}
            .label {{ color: #666; font-weight: 500; }}
            a {{ color: #0066cc; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .showtimes-section {{ background: white; padding: 24px; border-radius: 8px; margin-top: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .showtimes-section h2 {{ margin: 0 0 16px 0; color: #333; }}
            .date-header {{ color: #555; font-size: 16px; margin: 0 0 16px 0; padding-bottom: 8px; border-bottom: 1px solid #eee; }}
            .movie-showtimes {{ display: flex; gap: 16px; margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #f0f0f0; }}
            .movie-showtimes:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
            .movie-poster {{ width: 80px; height: 120px; object-fit: cover; border-radius: 4px; }}
            .movie-poster-placeholder {{ width: 80px; height: 120px; background: #e0e0e0; display: flex; align-items: center; justify-content: center; color: #999; font-size: 32px; border-radius: 4px; }}
            .movie-link {{ text-decoration: none; }}
            .movie-details {{ flex: 1; }}
            .movie-title {{ font-weight: 600; color: #333; margin-bottom: 12px; font-size: 18px; }}
            .movie-title a {{ color: inherit; }}
            .times {{ display: flex; flex-wrap: wrap; gap: 8px; }}
            .time {{ background: #0066cc; color: white; padding: 6px 12px; border-radius: 4px; font-size: 14px; }}
            .format {{ font-size: 11px; opacity: 0.8; }}
            .no-showtimes {{ color: #888; font-style: italic; }}
        </style>
    </head>
    <body>
        <div class="banner">
            <h1>🎬 Cine Medallo</h1>
            <div class="subtitle">Movie showtimes in Medellín</div>
            <nav>
                <a href="/">Movies</a>
                <a href="/theaters/">Theaters Near You</a>
            </nav>
        </div>
        <div class="container">
            <div class="theater-card">
                <h2>{t.name}</h2>
                <div class="chain">{t.chain}</div>

                <div class="info"><span class="label">Address:</span> {t.address}</div>
                <div class="info"><span class="label">City:</span> {t.city}</div>
                <div class="info"><span class="label">Neighborhood:</span> {t.neighborhood or 'N/A'}</div>
                <div class="info"><span class="label">Phone:</span> {t.phone or 'N/A'}</div>
                <div class="info"><span class="label">Screens:</span> {t.screen_count or 'N/A'}</div>
                <div class="info"><span class="label">Website:</span> {f'<a href="{t.website}" target="_blank">{t.website}</a>' if t.website else 'N/A'}</div>
            </div>

            <div class="showtimes-section">
                <h2>🎬 Today's Showtimes</h2>
                {showtimes_html}
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)


def movie_list(request):
    """Return a list of all movies."""
    movies = Movie.objects.all().order_by("-year", "title_es")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cine Medallo</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f5f5f5; }
            .banner { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 24px 40px; margin-bottom: 24px; }
            .banner h1 { margin: 0; font-size: 32px; }
            .banner .subtitle { color: #aaa; margin-top: 4px; }
            .banner nav { margin-top: 16px; }
            .banner nav a { color: #f5c518; text-decoration: none; margin-right: 24px; font-weight: 500; }
            .banner nav a:hover { text-decoration: underline; }
            .content { padding: 0 40px 40px 40px; }
            h2 { color: #333; margin-top: 0; }
            .movies { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
            .movie { background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .movie-poster { width: 100%; height: 400px; object-fit: cover; background: #ddd; }
            .movie-poster-placeholder { width: 100%; height: 400px; background: #e0e0e0; display: flex; align-items: center; justify-content: center; color: #999; font-size: 48px; }
            .movie-info { padding: 16px; }
            .movie-title { font-size: 18px; font-weight: 600; margin: 0 0 4px 0; color: #333; }
            .movie-original { font-size: 14px; color: #666; margin-bottom: 8px; font-style: italic; }
            .movie-year { font-size: 14px; color: #888; margin-bottom: 8px; }
            .movie-rating { font-size: 14px; color: #f5c518; margin-bottom: 8px; }
            .movie-synopsis { font-size: 13px; color: #555; line-height: 1.4; }
            .movie-links { margin-top: 12px; font-size: 13px; }
            .movie-links a { color: #0066cc; text-decoration: none; margin-right: 12px; }
            .movie-links a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="banner">
            <h1>🎬 Cine Medallo</h1>
            <div class="subtitle">Movie showtimes in Medellín</div>
            <nav>
                <a href="/">Movies</a>
                <a href="/theaters/">Theaters Near You</a>
            </nav>
        </div>
        <div class="content">
            <h2>Now Showing (""" + str(movies.count()) + """ movies)</h2>
            <div class="movies">
    """

    for m in movies:
        year_str = f"({m.year})" if m.year else ""
        rating_str = f"⭐ {m.tmdb_rating}/10" if m.tmdb_rating else ""
        original_title = f'<div class="movie-original">{m.original_title}</div>' if m.original_title and m.original_title != m.title_es else ""
        synopsis = m.synopsis[:200] + "..." if m.synopsis and len(m.synopsis) > 200 else (m.synopsis or "")

        if m.poster_url:
            poster_html = f'<img class="movie-poster" src="{m.poster_url}" alt="{m.title_es}">'
        else:
            poster_html = '<div class="movie-poster-placeholder">🎬</div>'

        links = []
        if m.tmdb_url:
            links.append(f'<a href="{m.tmdb_url}" target="_blank">TMDB</a>')
        if m.imdb_url:
            links.append(f'<a href="{m.imdb_url}" target="_blank">IMDB</a>')
        links_html = f'<div class="movie-links">{" ".join(links)}</div>' if links else ""

        html += f"""
        <div class="movie">
            <a href="/movies/{m.slug}/" style="text-decoration: none; color: inherit;">
                {poster_html}
            </a>
            <div class="movie-info">
                <h2 class="movie-title"><a href="/movies/{m.slug}/" style="text-decoration: none; color: inherit;">{m.title_es}</a></h2>
                {original_title}
                <div class="movie-year">{year_str}</div>
                <div class="movie-rating">{rating_str}</div>
                <div class="movie-synopsis">{synopsis}</div>
                {links_html}
            </div>
        </div>
        """

    html += "</div></div></body></html>"
    return HttpResponse(html)


def movie_detail(request, slug):
    """Return details for a single movie with all showtimes."""
    try:
        movie = Movie.objects.get(slug=slug)
    except Movie.DoesNotExist:
        return HttpResponse("<h1>Movie not found</h1>", status=404)

    from datetime import date as date_class

    today = date_class.today()
    showtimes = (
        Showtime.objects.filter(movie=movie, start_date=today)
        .select_related("theater")
        .order_by("theater__name", "start_time")
    )

    year_str = f"({movie.year})" if movie.year else ""
    rating_str = f"⭐ {movie.tmdb_rating}/10" if movie.tmdb_rating else ""
    duration_str = f"{movie.duration_minutes} min" if movie.duration_minutes else ""
    original_title = f"<p><em>{movie.original_title}</em></p>" if movie.original_title and movie.original_title != movie.title_es else ""

    if movie.poster_url:
        poster_html = f'<img class="poster" src="{movie.poster_url}" alt="{movie.title_es}">'
    else:
        poster_html = '<div class="poster-placeholder">🎬</div>'

    links = []
    if movie.tmdb_url:
        links.append(f'<a href="{movie.tmdb_url}" target="_blank">TMDB</a>')
    if movie.imdb_url:
        links.append(f'<a href="{movie.imdb_url}" target="_blank">IMDB</a>')
    links_html = f'<div class="links">{" ".join(links)}</div>' if links else ""

    # Group showtimes by theater
    showtimes_by_theater: dict[str, list[Showtime]] = {}
    for st in showtimes:
        theater_name = st.theater.name
        if theater_name not in showtimes_by_theater:
            showtimes_by_theater[theater_name] = []
        showtimes_by_theater[theater_name].append(st)

    today_str = today.strftime("%A, %B %d, %Y")
    showtimes_html = ""
    if showtimes_by_theater:
        showtimes_html += f'<h3 class="date-header">{today_str}</h3>'
        for theater_name, times in showtimes_by_theater.items():
            times_list = []
            for st in times:
                time_str = st.start_time.strftime("%I:%M %p").lstrip("0")
                format_str = f' <span class="format">({st.format})</span>' if st.format else ""
                times_list.append(f'<span class="time">{time_str}{format_str}</span>')
            showtimes_html += f'''
            <div class="theater-showtimes">
                <div class="theater-name">{theater_name}</div>
                <div class="times">{" ".join(times_list)}</div>
            </div>
            '''
    else:
        showtimes_html = '<p class="no-showtimes">No showtimes available for today</p>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{movie.title_es} - Cine Medallo</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f5f5f5; }}
            .banner {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 24px 40px; margin-bottom: 24px; }}
            .banner h1 {{ margin: 0; font-size: 32px; }}
            .banner .subtitle {{ color: #aaa; margin-top: 4px; }}
            .banner nav {{ margin-top: 16px; }}
            .banner nav a {{ color: #f5c518; text-decoration: none; margin-right: 24px; font-weight: 500; }}
            .banner nav a:hover {{ text-decoration: underline; }}
            .container {{ max-width: 1000px; margin: 0 auto; padding: 0 40px 40px 40px; }}
            .movie-header {{ display: flex; gap: 32px; background: white; padding: 24px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .poster {{ width: 300px; height: 450px; object-fit: cover; border-radius: 8px; }}
            .poster-placeholder {{ width: 300px; height: 450px; background: #e0e0e0; display: flex; align-items: center; justify-content: center; color: #999; font-size: 72px; border-radius: 8px; }}
            .movie-info h1 {{ margin: 0 0 8px 0; color: #333; }}
            .movie-info p {{ margin: 0 0 8px 0; color: #666; }}
            .meta {{ color: #888; font-size: 14px; margin-bottom: 16px; }}
            .synopsis {{ color: #444; line-height: 1.6; margin-top: 16px; }}
            .links {{ margin-top: 16px; }}
            .links a {{ color: #0066cc; text-decoration: none; margin-right: 16px; }}
            .links a:hover {{ text-decoration: underline; }}
            .showtimes-section {{ background: white; padding: 24px; border-radius: 8px; margin-top: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .showtimes-section h2 {{ margin: 0 0 16px 0; color: #333; }}
            .date-header {{ color: #555; font-size: 16px; margin: 24px 0 12px 0; padding-bottom: 8px; border-bottom: 1px solid #eee; }}
            .date-header:first-child {{ margin-top: 0; }}
            .theater-showtimes {{ margin-bottom: 16px; }}
            .theater-name {{ font-weight: 600; color: #333; margin-bottom: 8px; }}
            .times {{ display: flex; flex-wrap: wrap; gap: 8px; }}
            .time {{ background: #0066cc; color: white; padding: 6px 12px; border-radius: 4px; font-size: 14px; }}
            .format {{ font-size: 11px; opacity: 0.8; }}
            .no-showtimes {{ color: #888; font-style: italic; }}
        </style>
    </head>
    <body>
        <div class="banner">
            <h1>🎬 Cine Medallo</h1>
            <div class="subtitle">Movie showtimes in Medellín</div>
            <nav>
                <a href="/">Movies</a>
                <a href="/theaters/">Theaters Near You</a>
            </nav>
        </div>
        <div class="container">
            <div class="movie-header">
                {poster_html}
                <div class="movie-info">
                    <h1>{movie.title_es}</h1>
                    {original_title}
                    <div class="meta">
                        {year_str} {f"· {duration_str}" if duration_str else ""} {f"· {movie.genre}" if movie.genre else ""} {f"· {movie.age_rating}" if movie.age_rating else ""}
                    </div>
                    <div>{rating_str}</div>
                    <div class="synopsis">{movie.synopsis or ""}</div>
                    {links_html}
                </div>
            </div>

            <div class="showtimes-section">
                <h2>🎬 Today's Showtimes</h2>
                {showtimes_html}
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)

