import sys, argparse, os, csv, re
import urllib.parse, urllib.request
import xml.etree.ElementTree as et
from bs4 import BeautifulSoup as bs

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
            * Valid OpenHub API key

        Example of usage:
            python3 scrape.py [-i "projects_to_extract.txt"] [-t "some_openhub_tag"] > results.csv
    ''' 
    params = urllib.parse.urlencode({"api_key" : api_key, "v" : 1})
    if os.path.exists(input_file):
        csvwriter = csv.writer(sys.stdout, delimiter=",", quotechar="|", quoting=csv.QUOTE_MINIMAL)
        csvwriter.writerow(["ID", "NAME", "WEBSITE", "USER_COUNT", "YEAR_CONTRIBUTORS", "YEAR_COMMITS", 
                            "MAIN_LANGUAGE", "ACTIVITY", "ACTIVITY_INDX", "FIRST_COMMIT", "MOST_RECENT_COMMIT", "FACTOIDS"])
        with open(input_file, "r") as f:
            try:
                for line in f:
                    foss_name = line.rstrip("\n")
                    # supply url for every FOSS
                    url = "https://www.openhub.net/p/%s.xml?%s" % (foss_name, params)
                    req = urllib.request.urlopen(url)
                    tree = et.parse(req)
                    #check for errors
                    elem = tree.getroot()
                    error = elem.find("error")
                    if error != None:
                        print("ERROR retrieving url: %s" % url, file=sys.stderr)
                        print("OpenHub returned an error: %s" % et.tostring(error), file=sys.stderr)
                    # retrieve tags
                    tags_node = elem.find("result/project/tags")
                    if tags_node != None:
                        for node in tags_node:
                            if tag_pattern.match(node.text):
                                # get tags and write csv
                                _id = retrieve_tag(elem, "result/project/id")
                                name = retrieve_tag(elem, "result/project/name")
                                website = retrieve_tag(elem, "result/project/homepage_url")
                                
                                #---------- 
                                #user_count = retrieve_tag(elem, "result/project/user_count")
                                #
                                user_count = retrieve_real_user_counts(foss_name)
                                #---------- 

                                year_contribs = retrieve_tag(elem, "result/project/analysis/twelve_month_contributor_count")
                                year_commits = retrieve_tag(elem, "result/project/analysis/twelve_month_commit_count")
                                lang = retrieve_tag(elem, "result/project/analysis/main_language_name")
                                activity = retrieve_tag(elem, "result/project/project_activity_index/description")
                                activity_indx = retrieve_tag(elem, "result/project/project_activity_index/value")
                                first_commit_month = retrieve_tag(elem, "result/project/analysis/min_month") 
                                last_commit_month = retrieve_tag(elem, "result/project/analysis/max_month") 
                                factoids = ""
                                for factoid in elem.find("result/project/analysis/factoids").iter("factoid"):
                                    if factoid != None:
                                        line = re.sub(",", "", factoid.text)
                                        factoids += "%s - " % line.strip("\r\n\t")

                                csvwriter.writerow([_id, name, website, user_count, year_contribs, year_commits, lang, 
                                                    activity, activity_indx, first_commit_month, last_commit_month, factoids])
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
        #
        response = urllib.request.urlopen("https://www.openhub.net/p/%s/users?page=%s" % (foss_name, user_count_pages))
        soup = bs(response.read(), "lxml")
        last_page_users = len(soup.findAll("div", {"class" : "avatar"}))
        user_count = (user_count_pages-1)*10 + last_page_users
        #
    return user_count


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