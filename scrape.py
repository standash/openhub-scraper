import sys, argparse, os, csv, re
import urllib.request
import xml.etree.ElementTree as et
from bs4 import BeautifulSoup as bs
from dateutil.parser import parse

def retrieve_tag(elem, path):
	''' A helper method for retrieving XML tags
	'''
	tag = elem.find(path)
	txt = tag.text if tag != None else "N/A"
	return txt

def scrape_openhub(input_file, api_key):
	''' This script gets the information about selected FOSS from openhub.net (former ohloh) 
		using ohloh API (https://github.com/blackducksw/ohloh_api).

		Please provide the following files:
			* The FOSS projects of interest are either specified in ./input/foss-projects.txt or using a cli parameter
			* The OpenHub api key must be provided in ./key/openhub_key.txt

		Requirements:
			* Python 3.x
			* BeautifulSoup4
			* lxml
			* Valid OpenHub API key

		Example of usage:
			python3 scrape.py [-i "projects_to_extract.txt"] [-t "some_openhub_tag"] > results.csv
	''' 
	if os.path.exists(input_file):
		csvwriter = csv.writer(sys.stdout, delimiter=",", quotechar=" ", quoting=csv.QUOTE_MINIMAL)
		csvwriter.writerow(["ID", "NAME", "YEARS", "MAIN_LANG", "USER_COUNT", "CONTRIBS", "COMMITS", "LOCS_ADDED", "LOCS_REMOVED", "FILES_MODIFIED",
							"LOCS_JAVA", "LOCS_C", "LOCS_CPP", "LOCS_PHP", "LOCS_JS", "LOCS_SQL", "LOCS_BUCKET",
							"NO_MANAGED_LANG", "SCRIPTING_LANG", "UNPOPULAR_MAIN_LANG", "HAS_UNPOPULAR_LANG",
							"WEBSITE", "REPOSITORIES"])

		with open(input_file, "r") as f:
			try:
				for line in f:
					foss_name = line.rstrip("\n")
					url = "https://www.openhub.net/p/%s.xml?api_key=%s" % (foss_name, api_key)
					response = urllib.request.urlopen(url)
					tree = et.parse(response)
					elem = tree.getroot()
					error = elem.find("error")
					if error != None:
						print("ERROR retrieving url: %s" % url, file=sys.stderr)
						print("OpenHub returned an error: %s" % et.tostring(error), file=sys.stderr)
					tags_node = elem.find("result/project/tags")
					if tags_node != None:
						for node in tags_node:
							if tag_pattern.match(node.text):
								# ---------- 
								# parse XML first
								#---------- 
								_id = retrieve_tag(elem, "result/project/id")
								name = retrieve_tag(elem, "result/project/name")
								website = retrieve_tag(elem, "result/project/homepage_url")
								first_commit = retrieve_tag(elem, "result/project/analysis/min_month") 
								last_commit = retrieve_tag(elem, "result/project/analysis/max_month") 
								years = parse(last_commit).year - parse(first_commit).year
								main_lang = retrieve_tag(elem, "result/project/analysis/main_language_name")

								#---------- 
								# get stuff that is missing in XML from the HTML of a web page
								#---------- 
								top_languages = {"Java" : 0, "C" : 0, "C++" : 0, "PHP" : 0, "JavaScript" : 0, "SQL" : 0, "bucket" : 0}
								user_count = retrieve_real_user_counts(foss_name)
								(contribs, commits, locs_added, locs_removed, files_modified) = retrieve_repository_stats(foss_name)
								locs = retrieve_locs(foss_name, top_languages)
								no_managed_lang = 1 if (int(locs["C"]) + int(locs["C++"]) > 0) else 0
								scripting_lang = 1 if (int(locs["PHP"]) + int(locs["JavaScript"]) > 0) else 0
								unpopular_main_lang = 0 if main_lang in top_languages.keys() else 1
								has_unpopular_lang = 1 if (int(locs["bucket"]) > 0) else 0

								repos = retrieve_repositories(foss_name, api_key)
								repositories = ""
								for url in repos:
									repositories += "%s " % url
								# ---------- 
								csvwriter.writerow([_id, name, years, main_lang, user_count, contribs, commits, locs_added, locs_removed, files_modified, 
													locs["Java"], locs["C"], locs["C++"], locs["PHP"], locs["JavaScript"], locs["SQL"], locs["bucket"],
													no_managed_lang, scripting_lang, unpopular_main_lang, has_unpopular_lang,
													website, repositories])
								break
			except Exception as exception:
				print("ERROR: can't retrieve data from OpenHub --> %s" % exception, file=sys.stderr)
				print("\t---> Error rertieving project %s" % foss_name, file=sys.stderr)


def retrieve_real_user_counts(foss_name):
	''' I had to make this dirty hack because openhub has a bug in showing wrong usage numbers in xml
	'''
	user_count = 0
	response = urllib.request.urlopen("https://www.openhub.net/p/%s/users" % foss_name) 
	soup = bs(response.read(), "lxml")
	label = soup.find("label", {"class" : "paginate"})
	if label != None:
		label_txt = re.sub(",", "", label.text)
		pattern = re.compile(r"(\d+)(?!.*\d)")
		user_count_pages = int(pattern.search(label_txt).group())
		response = urllib.request.urlopen("https://www.openhub.net/p/%s/users?page=%s" % (foss_name, user_count_pages))
		soup = bs(response.read(), "lxml")
		last_page_users = len(soup.findAll("div", {"class" : "avatar"}))
		user_count = (user_count_pages-1)*10 + last_page_users
	return user_count


def retrieve_locs(foss_name, top_languages):
	''' Retrieves LOCS for X most popular languages (the rest is aggregated in "LOCS_BUCKET")
	'''
	response = urllib.request.urlopen("https://www.openhub.net/p/%s/analyses/latest/languages_summary" % foss_name) 
	soup = bs(response.read(), "lxml")
	rows = soup.find("table", {"id" : "analyses_language_table"}).findAll("tr")
	bucket = 0
	for row in rows:
		if row.has_attr("class"):
			lang = row.find("a").text
			locs = re.sub(",", "", row.find("td", {"class" : "center"}).text)
			if lang in top_languages:
				top_languages[lang] = int(locs)
			else:
				bucket += int(locs)
	top_languages["bucket"] = bucket
	return top_languages



def retrieve_repositories(foss_name, api_key):
	''' Retrieves the list of source code repositories
	'''
	url = "https://www.openhub.net/p/%s/enlistments.xml?api_key=%s" % (foss_name, api_key)
	response = urllib.request.urlopen(url)
	tree = et.parse(response)
	root = tree.getroot()
	enlistments = root.find("result").findall("enlistment") 
	urls = []
	if enlistments != None:
		for enlistment in enlistments:
			for repo in enlistment.findall("repository"):
				urls.append(retrieve_tag(repo,"url"))
	return urls

def retrieve_repository_stats(foss_name):
	''' Retrieves total number of commits and commiters (for all time) 
	'''
	url = "https://www.openhub.net/projects/%s/commits/summary" % foss_name
	response = urllib.request.urlopen(url)
	soup = bs(response.read(), "lxml")
	commits = soup.find("td", text="Commits:").find_next_sibling("td").text
	contribs = soup.find("td", text="Contributors:").find_next_sibling("td").text
	files_modified = soup.find("td", text="Files Modified:").find_next_sibling("td").text
	locs_added = soup.find("td", text="Lines Added:").find_next_sibling("td").text
	locs_removed = soup.find("td", text="Lines Removed").find_next_sibling("td").text
	return (contribs, commits, locs_added, locs_removed, files_modified)


if __name__ == "__main__":
	# process input arguments
	arg_parser = argparse.ArgumentParser(description="Available parameters:")
	arg_parser.add_argument("-i", type=str, help="Input file with FOSS project names to extract")
	arg_parser.add_argument("-t", type=str, help="Get only projects that have a specific tag on OpenHub")

	args = arg_parser.parse_args()
	
	input_file = args.i if args.i != None else "./input/foss-projects.txt"
	tag_pattern = args.t if args.t else ".*"
	tag_pattern = re.compile(".*%s.*" % tag_pattern, re.IGNORECASE)

	# retrieve the api_key
	api_key = ""
	api_key_filename = "./key/openhub_key.txt"
	if os.path.exists(api_key_filename):
		with open(api_key_filename, "r") as f:
			try:
				api_key = f.readline()
			except:
				print("ERROR: can't read the api key file at '%s'" % api_key_filename, file=sys.stderr)
	else:
		print("ERROR: OpenHub api key file is missing", file=sys.stderr)
		sys.exit()

	# get data from OpenHub
	scrape_openhub(input_file, api_key)
