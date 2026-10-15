from collector.sources.jobs import JobPostings
from collector.sources.reddit import RedditPosts
from collector.sources.weather import Weather

# Register sources here. The runner picks them up automatically.
ALL_SOURCES = [JobPostings, Weather, RedditPosts]
