from django.contrib import admin

from movies_app.models import UnfindableMovieUrl


@admin.register(UnfindableMovieUrl)
class UnfindableMovieUrlAdmin(admin.ModelAdmin):
    list_display = ["movie_title", "original_title", "reason", "attempts", "last_seen"]
    list_filter = ["reason", "last_seen"]
    search_fields = ["movie_title", "original_title", "url"]
    readonly_fields = ["first_seen", "last_seen", "attempts"]
    ordering = ["-last_seen"]
    actions = ["delete_selected", "reset_for_retry"]

    @admin.action(description="Reset selected URLs for retry (delete from cache)")
    def reset_for_retry(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"Deleted {count} unfindable URL(s). They will be retried on next scrape.")
