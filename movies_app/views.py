from django.http import HttpResponse

from movies_app.models import Movie, Showtime, Theater


def theater_list(request):
    """Return a list of all active theaters."""
    theaters = Theater.objects.filter(is_active=True).order_by("city", "name")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Theaters</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; }
            h1 { color: #333; }
            .theater { border: 1px solid #ddd; padding: 16px; margin-bottom: 16px; border-radius: 8px; }
            .theater h2 { margin: 0 0 8px 0; font-size: 18px; }
            .theater h2 a { color: #0066cc; text-decoration: none; }
            .theater h2 a:hover { text-decoration: underline; }
            .chain { color: #666; font-size: 14px; margin-bottom: 8px; }
            .address { color: #444; }
            .details { color: #666; font-size: 14px; margin-top: 8px; }
        </style>
    </head>
    <body>
        <h1>Theaters (""" + str(theaters.count()) + """)</h1>
    """

    current_city = None
    for t in theaters:
        if t.city != current_city:
            if current_city is not None:
                html += "</div>"
            current_city = t.city
            html += f"<h2 style='margin-top: 32px; color: #555;'>{t.city}</h2><div>"

        html += f"""
        <div class="theater">
            <h2><a href="/api/theaters/{t.slug}/">{t.name}</a></h2>
            <div class="chain">{t.chain}</div>
            <div class="address">{t.address}</div>
            <div class="details">
                {t.neighborhood}
                {f' · {t.screen_count} screens' if t.screen_count else ''}
                {f' · <a href="{t.website}" target="_blank">Website</a>' if t.website else ''}
            </div>
        </div>
        """

    html += "</div></body></html>"
    return HttpResponse(html)


def theater_detail(request, slug):
    """Return details for a single theater by slug."""
    try:
        t = Theater.objects.get(slug=slug, is_active=True)
    except Theater.DoesNotExist:
        return HttpResponse("<h1>Theater not found</h1>", status=404)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{t.name}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; }}
            h1 {{ color: #333; margin-bottom: 8px; }}
            .chain {{ color: #666; font-size: 18px; margin-bottom: 24px; }}
            .info {{ margin-bottom: 12px; }}
            .label {{ color: #666; font-weight: 500; }}
            a {{ color: #0066cc; }}
            .back {{ margin-top: 32px; }}
        </style>
    </head>
    <body>
        <h1>{t.name}</h1>
        <div class="chain">{t.chain}</div>

        <div class="info"><span class="label">Address:</span> {t.address}</div>
        <div class="info"><span class="label">City:</span> {t.city}</div>
        <div class="info"><span class="label">Neighborhood:</span> {t.neighborhood or 'N/A'}</div>
        <div class="info"><span class="label">Phone:</span> {t.phone or 'N/A'}</div>
        <div class="info"><span class="label">Screens:</span> {t.screen_count or 'N/A'}</div>
        <div class="info"><span class="label">Website:</span> {f'<a href="{t.website}" target="_blank">{t.website}</a>' if t.website else 'N/A'}</div>

        <div class="back"><a href="/api/theaters/">← Back to all theaters</a></div>
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

        movie_id = m.id  # pyright: ignore[reportAttributeAccessIssue]
        html += f"""
        <div class="movie">
            <a href="/movies/{movie_id}/" style="text-decoration: none; color: inherit;">
                {poster_html}
            </a>
            <div class="movie-info">
                <h2 class="movie-title"><a href="/movies/{movie_id}/" style="text-decoration: none; color: inherit;">{m.title_es}</a></h2>
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


def movie_detail(request, movie_id):
    """Return details for a single movie with all showtimes."""
    try:
        movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        return HttpResponse("<h1>Movie not found</h1>", status=404)

    showtimes = (
        Showtime.objects.filter(movie=movie)
        .select_related("theater")
        .order_by("start_date", "theater__name", "start_time")
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

    # Group showtimes by date, then by theater
    showtimes_by_date: dict[str, dict[str, list[Showtime]]] = {}
    for st in showtimes:
        date_key = st.start_date.strftime("%A, %B %d, %Y")
        theater_name = st.theater.name
        if date_key not in showtimes_by_date:
            showtimes_by_date[date_key] = {}
        if theater_name not in showtimes_by_date[date_key]:
            showtimes_by_date[date_key][theater_name] = []
        showtimes_by_date[date_key][theater_name].append(st)

    showtimes_html = ""
    if showtimes_by_date:
        for date_str, theaters in showtimes_by_date.items():
            showtimes_html += f'<h3 class="date-header">{date_str}</h3>'
            for theater_name, times in theaters.items():
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
        showtimes_html = '<p class="no-showtimes">No showtimes available</p>'

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
                <h2>🎬 Showtimes</h2>
                {showtimes_html}
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)

