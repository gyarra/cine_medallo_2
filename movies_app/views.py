from django.http import HttpResponse

from movies_app.models import Movie, Showtime, Theater


def theater_list(request):
    """Return a list of all active theaters."""
    theaters = Theater.objects.filter(is_active=True).order_by("city", "name")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cines - Cine Medallo</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f0f0f0; color: #333; }
            .header { background: #1a1a1a; display: flex; align-items: center; justify-content: space-between; padding: 16px 40px; border-bottom: 1px solid #333; }
            .logo { display: flex; align-items: center; gap: 12px; text-decoration: none; }
            .logo-stripes { display: flex; gap: 4px; }
            .logo-stripes span { display: block; width: 8px; height: 40px; background: #e63946; border-radius: 2px; }
            .logo-text { font-size: 24px; font-weight: 700; letter-spacing: 1px; }
            .logo-text .cine { color: #fff; }
            .logo-text .medallo { color: #e63946; }
            .header nav { display: flex; gap: 32px; }
            .header nav a { color: #888; text-decoration: none; font-size: 14px; font-weight: 500; letter-spacing: 1px; text-transform: uppercase; transition: color 0.2s; }
            .header nav a:hover, .header nav a.active { color: #fff; }
            .content { padding: 32px 40px; }
            h2 { color: #333; margin-top: 0; }
            .city-header { margin-top: 32px; color: #666; font-size: 20px; border-bottom: 2px solid #ddd; padding-bottom: 8px; }
            .city-header:first-child { margin-top: 0; }
            .theaters-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 16px; margin-top: 16px; }
            .theater { background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .theater h3 { margin: 0 0 8px 0; font-size: 18px; }
            .theater h3 a { color: #e63946; text-decoration: none; }
            .theater h3 a:hover { text-decoration: underline; }
            .chain { color: #888; font-size: 13px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
            .address { color: #555; font-size: 14px; }
            .details { color: #888; font-size: 13px; margin-top: 8px; }
            .details a { color: #e63946; }
        </style>
    </head>
    <body>
        <header class="header">
            <a href="/" class="logo">
                <div class="logo-stripes"><span></span><span></span><span></span></div>
                <div class="logo-text"><span class="cine">CINE</span><span class="medallo">MEDALLO</span></div>
            </a>
            <nav>
                <a href="/">Cartelera</a>
                <a href="/theaters/" class="active">Cines</a>
            </nav>
        </header>
        <div class="content">
            <h2>Cines (""" + str(theaters.count()) + """)</h2>
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
                {f' · {t.screen_count} salas' if t.screen_count else ''}
                {f' · <a href="{t.website}" target="_blank">Sitio web</a>' if t.website else ''}
            </div>
        </div>
        """

    html += "</div></div></body></html>"
    return HttpResponse(html)


def theater_detail(request, slug):
    """Return details for a single theater by slug."""
    import datetime
    import zoneinfo

    bogota_tz = zoneinfo.ZoneInfo("America/Bogota")

    try:
        t = Theater.objects.get(slug=slug, is_active=True)
    except Theater.DoesNotExist:
        return HttpResponse("<h1>Theater not found</h1>", status=404)

    today = datetime.datetime.now(bogota_tz).date()
    showtimes = (
        Showtime.objects.filter(theater=t, start_date__gte=today)
        .select_related("movie")
        .order_by("start_date", "movie__title_es", "start_time")
    )

    showtimes_by_date: dict[datetime.date, dict[int, dict]] = {}
    for st in showtimes:
        if st.start_date not in showtimes_by_date:
            showtimes_by_date[st.start_date] = {}

        movie_id = st.movie.id  # pyright: ignore[reportAttributeAccessIssue]
        if movie_id not in showtimes_by_date[st.start_date]:
            showtimes_by_date[st.start_date][movie_id] = {
                "movie": st.movie,
                "times": [],
            }
        showtimes_by_date[st.start_date][movie_id]["times"].append(st)

    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

    showtimes_html = ""
    if showtimes_by_date:
        for showtime_date in sorted(showtimes_by_date.keys()):
            movies_for_date = showtimes_by_date[showtime_date]
            dia = dias_semana[showtime_date.weekday()]
            mes = meses[showtime_date.month - 1]
            fecha_str = f"{dia}, {showtime_date.day} de {mes}"
            if showtime_date == today:
                date_label = f"Hoy - {fecha_str}"
            else:
                date_label = fecha_str

            movies_html = ""
            for movie_data in movies_for_date.values():
                movie = movie_data["movie"]
                times = movie_data["times"]
                times_list = []
                for st in times:
                    time_str = st.start_time.strftime("%I:%M %p").lstrip("0")
                    format_str = f' <span class="format">({st.format})</span>' if st.format else ""
                    times_list.append(f'<span class="time">{time_str}{format_str}</span>')

                poster_html = f'<img class="movie-poster" src="{movie.poster_url}" alt="{movie.title_es}">' if movie.poster_url else '<div class="movie-poster-placeholder">🎬</div>'
                movies_html += f'''
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

            showtimes_html += f'''
            <div class="date-card">
                <h3 class="date-header">{date_label}</h3>
                {movies_html}
            </div>
            '''
    else:
        showtimes_html = '<p class="no-showtimes">No hay funciones disponibles</p>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{t.name} - Cine Medallo</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f0f0f0; color: #333; }}
            .header {{ background: #1a1a1a; display: flex; align-items: center; justify-content: space-between; padding: 16px 40px; border-bottom: 1px solid #333; }}
            .logo {{ display: flex; align-items: center; gap: 12px; text-decoration: none; }}
            .logo-stripes {{ display: flex; gap: 4px; }}
            .logo-stripes span {{ display: block; width: 8px; height: 40px; background: #e63946; border-radius: 2px; }}
            .logo-text {{ font-size: 24px; font-weight: 700; letter-spacing: 1px; }}
            .logo-text .cine {{ color: #fff; }}
            .logo-text .medallo {{ color: #e63946; }}
            .header nav {{ display: flex; gap: 32px; }}
            .header nav a {{ color: #888; text-decoration: none; font-size: 14px; font-weight: 500; letter-spacing: 1px; text-transform: uppercase; transition: color 0.2s; }}
            .header nav a:hover, .header nav a.active {{ color: #fff; }}
            .container {{ max-width: 900px; margin: 0 auto; padding: 32px 40px; }}
            .theater-card {{ background: #fff; padding: 32px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .theater-card h2 {{ margin: 0 0 8px 0; color: #333; }}
            .chain {{ color: #888; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 24px; }}
            .info {{ margin-bottom: 12px; color: #555; }}
            .label {{ color: #888; font-weight: 500; }}
            a {{ color: #e63946; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .date-card {{ background: #fff; padding: 24px; border-radius: 8px; margin-top: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .date-header {{ color: #333; font-size: 18px; margin: 0 0 16px 0; padding-bottom: 12px; border-bottom: 2px solid #e63946; }}
            .movie-showtimes {{ display: flex; gap: 16px; margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #eee; }}
            .movie-showtimes:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
            .movie-poster {{ width: 80px; height: 120px; object-fit: cover; border-radius: 4px; }}
            .movie-poster-placeholder {{ width: 80px; height: 120px; background: #ddd; display: flex; align-items: center; justify-content: center; color: #999; font-size: 32px; border-radius: 4px; }}
            .movie-link {{ text-decoration: none; }}
            .movie-details {{ flex: 1; }}
            .movie-title {{ font-weight: 600; color: #333; margin-bottom: 12px; font-size: 18px; }}
            .movie-title a {{ color: inherit; }}
            .times {{ display: flex; flex-wrap: wrap; gap: 8px; }}
            .time {{ background: #e63946; color: white; padding: 6px 12px; border-radius: 4px; font-size: 14px; }}
            .format {{ font-size: 11px; opacity: 0.8; }}
            .no-showtimes {{ color: #888; font-style: italic; }}
        </style>
    </head>
    <body>
        <header class="header">
            <a href="/" class="logo">
                <div class="logo-stripes"><span></span><span></span><span></span></div>
                <div class="logo-text"><span class="cine">CINE</span><span class="medallo">MEDALLO</span></div>
            </a>
            <nav>
                <a href="/">Cartelera</a>
                <a href="/theaters/" class="active">Cines</a>
            </nav>
        </header>
        <div class="container">
            <div class="theater-card">
                <h2>{t.name}</h2>
                <div class="chain">{t.chain}</div>

                <div class="info"><span class="label">Dirección:</span> {t.address}</div>
                <div class="info"><span class="label">Ciudad:</span> {t.city}</div>
                <div class="info"><span class="label">Barrio:</span> {t.neighborhood or 'N/A'}</div>
                <div class="info"><span class="label">Teléfono:</span> {t.phone or 'N/A'}</div>
                <div class="info"><span class="label">Salas:</span> {t.screen_count or 'N/A'}</div>
                <div class="info"><span class="label">Sitio web:</span> {f'<a href="{t.website}" target="_blank">{t.website}</a>' if t.website else 'N/A'}</div>
            </div>

            {showtimes_html}
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
        <title>Cine Medallo - Cartelera</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f0f0f0; color: #333; }
            .header { background: #1a1a1a; display: flex; align-items: center; justify-content: space-between; padding: 16px 40px; border-bottom: 1px solid #333; }
            .logo { display: flex; align-items: center; gap: 12px; text-decoration: none; }
            .logo-stripes { display: flex; gap: 4px; }
            .logo-stripes span { display: block; width: 8px; height: 40px; background: #e63946; border-radius: 2px; }
            .logo-text { font-size: 24px; font-weight: 700; letter-spacing: 1px; }
            .logo-text .cine { color: #fff; }
            .logo-text .medallo { color: #e63946; }
            .header nav { display: flex; gap: 32px; }
            .header nav a { color: #888; text-decoration: none; font-size: 14px; font-weight: 500; letter-spacing: 1px; text-transform: uppercase; transition: color 0.2s; }
            .header nav a:hover, .header nav a.active { color: #fff; }
            .content { padding: 32px 40px; }
            h2 { color: #333; margin-top: 0; }
            .movies { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
            .movie { background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .movie-poster { width: 100%; height: 400px; object-fit: cover; background: #ddd; }
            .movie-poster-placeholder { width: 100%; height: 400px; background: #ddd; display: flex; align-items: center; justify-content: center; color: #999; font-size: 48px; }
            .movie-info { padding: 16px; }
            .movie-title { font-size: 18px; font-weight: 600; margin: 0 0 4px 0; color: #333; }
            .movie-original { font-size: 14px; color: #666; margin-bottom: 8px; font-style: italic; }
            .movie-year { font-size: 14px; color: #888; margin-bottom: 8px; }
            .movie-rating { font-size: 14px; color: #e63946; margin-bottom: 8px; }
            .movie-synopsis { font-size: 13px; color: #666; line-height: 1.4; }
            .movie-links { margin-top: 12px; font-size: 13px; }
            .movie-links a { color: #e63946; text-decoration: none; margin-right: 12px; }
            .movie-links a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <header class="header">
            <a href="/" class="logo">
                <div class="logo-stripes"><span></span><span></span><span></span></div>
                <div class="logo-text"><span class="cine">CINE</span><span class="medallo">MEDALLO</span></div>
            </a>
            <nav>
                <a href="/" class="active">Cartelera</a>
                <a href="/theaters/">Cines</a>
            </nav>
        </header>
        <div class="content">
            <h2>En Cartelera (""" + str(movies.count()) + """ películas)</h2>
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

    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    dia = dias_semana[today.weekday()]
    mes = meses[today.month - 1]
    today_str = f"{dia}, {today.day} de {mes} de {today.year}"
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
        showtimes_html = '<p class="no-showtimes">No hay funciones disponibles para hoy</p>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{movie.title_es} - Cine Medallo</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f0f0f0; color: #333; }}
            .header {{ background: #1a1a1a; display: flex; align-items: center; justify-content: space-between; padding: 16px 40px; border-bottom: 1px solid #333; }}
            .logo {{ display: flex; align-items: center; gap: 12px; text-decoration: none; }}
            .logo-stripes {{ display: flex; gap: 4px; }}
            .logo-stripes span {{ display: block; width: 8px; height: 40px; background: #e63946; border-radius: 2px; }}
            .logo-text {{ font-size: 24px; font-weight: 700; letter-spacing: 1px; }}
            .logo-text .cine {{ color: #fff; }}
            .logo-text .medallo {{ color: #e63946; }}
            .header nav {{ display: flex; gap: 32px; }}
            .header nav a {{ color: #888; text-decoration: none; font-size: 14px; font-weight: 500; letter-spacing: 1px; text-transform: uppercase; transition: color 0.2s; }}
            .header nav a:hover, .header nav a.active {{ color: #fff; }}
            .container {{ max-width: 1000px; margin: 0 auto; padding: 32px 40px; }}
            .movie-header {{ display: flex; gap: 32px; background: #fff; padding: 24px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .poster {{ width: 300px; height: 450px; object-fit: cover; border-radius: 8px; }}
            .poster-placeholder {{ width: 300px; height: 450px; background: #ddd; display: flex; align-items: center; justify-content: center; color: #999; font-size: 72px; border-radius: 8px; }}
            .movie-info h1 {{ margin: 0 0 8px 0; color: #333; }}
            .movie-info p {{ margin: 0 0 8px 0; color: #666; }}
            .meta {{ color: #888; font-size: 14px; margin-bottom: 16px; }}
            .synopsis {{ color: #555; line-height: 1.6; margin-top: 16px; }}
            .links {{ margin-top: 16px; }}
            .links a {{ color: #e63946; text-decoration: none; margin-right: 16px; }}
            .links a:hover {{ text-decoration: underline; }}
            .showtimes-section {{ background: #fff; padding: 24px; border-radius: 8px; margin-top: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .showtimes-section h2 {{ margin: 0 0 16px 0; color: #333; }}
            .date-header {{ color: #666; font-size: 16px; margin: 24px 0 12px 0; padding-bottom: 8px; border-bottom: 1px solid #eee; }}
            .date-header:first-child {{ margin-top: 0; }}
            .theater-showtimes {{ margin-bottom: 16px; }}
            .theater-name {{ font-weight: 600; color: #333; margin-bottom: 8px; }}
            .times {{ display: flex; flex-wrap: wrap; gap: 8px; }}
            .time {{ background: #e63946; color: white; padding: 6px 12px; border-radius: 4px; font-size: 14px; }}
            .format {{ font-size: 11px; opacity: 0.8; }}
            .no-showtimes {{ color: #888; font-style: italic; }}
        </style>
    </head>
    <body>
        <header class="header">
            <a href="/" class="logo">
                <div class="logo-stripes"><span></span><span></span><span></span></div>
                <div class="logo-text"><span class="cine">CINE</span><span class="medallo">MEDALLO</span></div>
            </a>
            <nav>
                <a href="/">Cartelera</a>
                <a href="/theaters/">Cines</a>
            </nav>
        </header>
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
                <h2>🎬 Horarios de Hoy</h2>
                {showtimes_html}
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)

