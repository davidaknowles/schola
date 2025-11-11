#!/usr/bin/env python3
"""
Script to fetch all publications for a given author from PubMed.
Retrieves detailed publication information including title, journal, year, DOI, and abstract.
"""

from Bio import Entrez
import csv
import json
from datetime import datetime
import argparse
import requests
import time

def fetch_author_publications(author_name, email, start_year=None, end_year=None, output_format='csv', filter_author_position=True):
    """
    Fetch all publications for a given author from PubMed.
    
    Args:
        author_name: Author name in format "LastName FirstInitial" (e.g., "Knowles DA")
        email: Email address for NCBI Entrez (required)
        start_year: Optional starting year to filter publications
        end_year: Optional ending year to filter publications
        output_format: Output format ('csv', 'json', or 'both')
        filter_author_position: If True, only include papers where author is in first 2 or last 2 positions
    
    Returns:
        List of publication dictionaries
    """
    Entrez.email = email
    
    # Extract the search author's last name once
    search_last_name = author_name.split()[0].upper()
    
    # Build search term
    term = f'"{author_name}[Author]"'
    if start_year or end_year:
        start = start_year or "1900"
        end = end_year or "3000"
        term += f' AND ("{start}"[dp] : "{end}"[dp])'
    
    print(f"Searching PubMed for: {term}")
    
    # Search for publications
    search = Entrez.esearch(db="pubmed", term=term, retmax=10000)
    result = Entrez.read(search)
    ids = result["IdList"]
    
    print(f"Found {len(ids)} publications")
    
    if not ids:
        return []
    
    # Fetch detailed records in batches to avoid memory issues
    print("Fetching publication details...")
    publications = []
    batch_size = 100
    
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i+batch_size]
        print(f"Fetching batch {i//batch_size + 1}/{(len(ids)-1)//batch_size + 1} ({len(batch_ids)} records)...")
        
        try:
            handle = Entrez.efetch(db="pubmed", id=",".join(batch_ids), retmode="xml")
            records = Entrez.read(handle)
            handle.close()
        except Exception as e:
            print(f"Error fetching batch: {e}")
            continue
    
        for record in records["PubmedArticle"]:
            try:
                article = record["MedlineCitation"]["Article"]
                pubmed_data = record.get("PubmedData", {})
                
                # Extract publication year
                pub_date = article["Journal"]["JournalIssue"]["PubDate"]
                year = pub_date.get("Year", "")
                if not year and "MedlineDate" in pub_date:
                    # Try to extract year from MedlineDate (e.g., "2020 Jan-Feb")
                    year = pub_date["MedlineDate"].split()[0]
                
                # Extract DOI
                doi = ""
                article_ids = pubmed_data.get("ArticleIdList", [])
                for article_id in article_ids:
                    if article_id.attributes.get("IdType") == "doi":
                        doi = str(article_id)
                        break
                
                # Extract PMID
                pmid = record["MedlineCitation"]["PMID"]
                
                # Extract title
                title = article.get("ArticleTitle", "")
                
                # Extract authors
                author_list = article.get("AuthorList", [])
                authors = []
                for author in author_list:
                    if "LastName" in author and "Initials" in author:
                        author_full_name = f"{author['LastName']} {author['Initials']}"
                        authors.append(author_full_name)
                    elif "CollectiveName" in author:
                        authors.append(author["CollectiveName"])
                authors_str = ", ".join(authors)
                
                # Check if searched author is in first two or last two positions
                author_position = None
                
                for idx, author in enumerate(author_list):
                    if "LastName" in author:
                        if author["LastName"].upper() == search_last_name:
                            author_position = idx
                            break
                
                # Optionally skip if author is not in first 2 or last 2 positions
                if filter_author_position:
                    if author_position is not None:
                        num_authors = len(authors)
                        is_first_two = author_position < 2
                        is_last_two = author_position >= num_authors - 2
                        
                        if not (is_first_two or is_last_two):
                            continue  # Skip this publication
                    else:
                        # If we couldn't find the author, skip (shouldn't happen)
                        continue
                
                # Extract abstract
                abstract = ""
                if "Abstract" in article and "AbstractText" in article["Abstract"]:
                    abstract_parts = article["Abstract"]["AbstractText"]
                    if isinstance(abstract_parts, list):
                        abstract = " ".join([str(part) for part in abstract_parts])
                    else:
                        abstract = str(abstract_parts)
                
                # Extract journal info
                journal = article["Journal"]["Title"]
                
                pub_info = {
                    "PMID": str(pmid),
                    "Title": str(title),
                    "Authors": authors_str,
                    "Journal": str(journal),
                    "Year": str(year),
                    "DOI": doi,
                    "Abstract": abstract,
                    "PubMed_URL": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                }
                
                publications.append(pub_info)
                
            except Exception as e:
                print(f"Error processing record: {e}")
                continue
    
    # Sort by year (most recent first)
    publications.sort(key=lambda x: x.get("Year", ""), reverse=True)
    
    # Fetch citation counts from NIH iCite
    print("\nFetching citation counts from NIH iCite...")
    fetch_citation_counts(publications)
    
    return publications


def fetch_citation_counts(publications):
    """
    Fetch citation counts from NIH iCite API for a list of publications.
    Updates the publications list in place.
    
    Args:
        publications: List of publication dictionaries with PMID
    """
    # Process in batches (iCite accepts up to 1000 PMIDs at once)
    batch_size = 1000
    pmids = [p["PMID"] for p in publications]
    
    for i in range(0, len(pmids), batch_size):
        batch_pmids = pmids[i:i+batch_size]
        pmid_str = ",".join(batch_pmids)
        
        try:
            url = f"https://icite.od.nih.gov/api/pubs"
            params = {"pmids": pmid_str, "format": "json"}
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                citation_map = {}
                
                for item in data.get("data", []):
                    pmid = str(item.get("pmid", ""))
                    citation_map[pmid] = {
                        "citation_count": item.get("citation_count", 0),
                        "relative_citation_ratio": item.get("relative_citation_ratio", ""),
                        "field_citation_rate": item.get("field_citation_rate", "")
                    }
                
                # Update publications with citation data
                for pub in publications:
                    if pub["PMID"] in citation_map:
                        cite_data = citation_map[pub["PMID"]]
                        pub["Citation_Count"] = cite_data["citation_count"]
                        pub["RCR"] = cite_data["relative_citation_ratio"]
                        pub["Field_Citation_Rate"] = cite_data["field_citation_rate"]
                    else:
                        pub["Citation_Count"] = ""
                        pub["RCR"] = ""
                        pub["Field_Citation_Rate"] = ""
                
                print(f"Retrieved citation data for batch {i//batch_size + 1}")
            else:
                print(f"Warning: iCite API returned status {response.status_code}")
                # Add empty citation fields
                for pub in publications:
                    if "Citation_Count" not in pub:
                        pub["Citation_Count"] = ""
                        pub["RCR"] = ""
                        pub["Field_Citation_Rate"] = ""
            
            time.sleep(0.5)  # Be nice to the API
            
        except Exception as e:
            print(f"Error fetching citation data: {e}")
            # Add empty citation fields on error
            for pub in publications:
                if "Citation_Count" not in pub:
                    pub["Citation_Count"] = ""
                    pub["RCR"] = ""
                    pub["Field_Citation_Rate"] = ""
    
    return publications


def save_publications(publications, author_name, output_format='csv'):
    """
    Save publications to file(s).
    
    Args:
        publications: List of publication dictionaries
        author_name: Author name for filename
        output_format: 'csv', 'json', 'html', or 'both'
    """
    # Clean author name for filename
    clean_name = author_name.replace(" ", "_").replace('"', '')
    timestamp = datetime.now().strftime("%Y%m%d")
    
    if output_format in ['csv', 'both']:
        csv_filename = f"{clean_name}_publications_{timestamp}.csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as f:
            if publications:
                writer = csv.DictWriter(f, fieldnames=publications[0].keys())
                writer.writeheader()
                writer.writerows(publications)
        print(f"Saved {len(publications)} publications to {csv_filename}")
    
    if output_format in ['json', 'both']:
        json_filename = f"{clean_name}_publications_{timestamp}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(publications, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(publications)} publications to {json_filename}")
    
    if output_format in ['html', 'both']:
        html_filename = f"{clean_name}_publications_{timestamp}.html"
        create_html_output(publications, html_filename, author_name)
        print(f"Saved {len(publications)} publications to {html_filename}")


def compute_imputed_metrics(publications):
    """Compute and attach imputed metrics (e.g., RCR_imputed) to publications list."""
    for pub in publications:
        if not pub.get("RCR") or pub.get("RCR") == "":
            year = pub.get("Year", "")
            citations = pub.get("Citation_Count", 0)
            if year and citations:
                try:
                    years_since = datetime.now().year - int(year)
                    if years_since > 0:
                        pub["RCR_imputed"] = citations / years_since
                    else:
                        pub["RCR_imputed"] = citations + 1
                except:
                    pub["RCR_imputed"] = 0
            else:
                pub["RCR_imputed"] = 0
        else:
            try:
                pub["RCR_imputed"] = float(pub["RCR"])
            except:
                pub["RCR_imputed"] = 1.5
    return publications


def highlight_authors(authors_str: str, author_name: str) -> str:
    """Bold the searched author within a comma-separated authors string."""
    parts = author_name.split()
    search_last = parts[0].lower() if parts else ""
    search_initials = "".join(parts[1:]).lower() if len(parts) > 1 else ""
    tokens = [t.strip() for t in (authors_str or "").split(",") if t.strip()]
    highlighted = []
    for t in tokens:
        segs = t.split()
        last = segs[0].lower() if segs else ""
        initials = "".join(segs[1:]).lower() if len(segs) > 1 else ""
        if last == search_last and (not search_initials or initials.startswith(search_initials)):
            highlighted.append(f"<strong>{t}</strong>")
        else:
            highlighted.append(t)
    return ", ".join(highlighted)


def build_html_content(publications, author_name):
    """Return HTML string for interactive publications page (no file I/O)."""
    # Impute missing RCR values for sorting (use citation count as proxy)
    for pub in publications:
        if not pub.get("RCR") or pub.get("RCR") == "":
            # For papers without RCR, estimate based on citations and years since publication
            year = pub.get("Year", "")
            citations = pub.get("Citation_Count", 0)
            if year and citations:
                try:
                    years_since = datetime.now().year - int(year)
                    if years_since > 0:
                        # Rough estimate: citations per year as a proxy for RCR
                        pub["RCR_imputed"] = citations / years_since
                    else:
                        pub["RCR_imputed"] = citations + 1  # strong bias towards recent papers
                except:
                    pub["RCR_imputed"] = 0
            else:
                pub["RCR_imputed"] = 0
        else:
            try:
                pub["RCR_imputed"] = float(pub["RCR"])
            except:
                pub["RCR_imputed"] = 1.5
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Publications - {author_name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
            line-height: 1.6;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
        }}
        .controls {{
            background: white;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .controls label {{
            margin-right: 10px;
            font-weight: 600;
        }}
        .controls select {{
            padding: 5px 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }}
        .publication {{
            background: white;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: box-shadow 0.3s;
        }}
        .publication:hover {{
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }}
        .title {{
            font-size: 18px;
            font-weight: 600;
            color: #0066cc;
            margin-bottom: 8px;
            cursor: pointer;
        }}
        .title:hover {{
            text-decoration: underline;
        }}
        .authors {{
            color: #555;
            margin-bottom: 5px;
            font-size: 14px;
        }}
        .meta {{
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        .journal {{
            font-style: italic;
        }}
        .metrics {{
            display: flex;
            gap: 20px;
            margin-bottom: 10px;
            font-size: 14px;
        }}
        .metric {{
            background: #f0f7ff;
            padding: 5px 10px;
            border-radius: 4px;
            border-left: 3px solid #0066cc;
        }}
        .metric strong {{
            color: #0066cc;
        }}
        .abstract {{
            display: none;
            margin-top: 15px;
            padding: 15px;
            background: #f9f9f9;
            border-left: 4px solid #0066cc;
            border-radius: 4px;
            color: #444;
            font-size: 14px;
        }}
        .abstract.show {{
            display: block;
        }}
        .links {{
            margin-top: 10px;
        }}
        .link {{
            display: inline-block;
            margin-right: 15px;
            color: #0066cc;
            text-decoration: none;
            font-size: 14px;
        }}
        .link:hover {{
            text-decoration: underline;
        }}
        .summary {{
            background: white;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <h1>Publications - {author_name}</h1>
    
    <div class="summary">
        <strong>Total Publications:</strong> {len(publications)} |
        <strong>Total Citations:</strong> {sum(int(p.get("Citation_Count", 0) or 0) for p in publications)}
    </div>
    
    <div class="controls">
        <label for="sortBy">Sort by:</label>
        <select id="sortBy" onchange="sortPublications()">
            <option value="year">Year (newest first)</option>
            <option value="citations">Citations (most cited first)</option>
            <option value="rcr" selected>RCR (highest first)</option>
        </select>
    </div>
    
    <div id="publications">
"""
    
    # Compute imputed metrics if needed
    compute_imputed_metrics(publications)

    # Add each publication
    for i, pub in enumerate(publications):
        year = pub.get("Year", "N/A")
        citations = pub.get("Citation_Count", "N/A")
        rcr = pub.get("RCR", "")
        rcr_imputed = pub.get("RCR_imputed", 0)
        title = pub.get("Title", "No title")
        authors = pub.get("Authors", "")
        authors_display = highlight_authors(authors, author_name)
        journal = pub.get("Journal", "")
        abstract = pub.get("Abstract", "No abstract available")
        pmid = pub.get("PMID", "")
        doi = pub.get("DOI", "")
        pubmed_url = pub.get("PubMed_URL", "")
        
        # Format RCR display: show imputed value when raw RCR missing
        try:
            rcr_num = float(rcr) if rcr not in (None, "", "N/A") else None
        except:
            rcr_num = None
        rcr_display = f"{(rcr_num if rcr_num is not None else rcr_imputed):.2f}" if (rcr_num is not None or rcr_imputed) else "N/A"
        
        html_content += f"""
        <div class="publication" data-year="{year}" data-citations="{citations if citations != 'N/A' else 0}" data-rcr="{rcr_imputed}">
            <div class="title" onclick="toggleAbstract({i})">{title}</div>
            <div class="authors">{authors_display}</div>
            <div class="meta">
                <span class="journal">{journal}</span> ({year})
            </div>
            <div class="metrics">
                <div class="metric"><strong>Citations:</strong> {citations}</div>
                <div class="metric"><strong>RCR:</strong> {rcr_display}</div>
            </div>
            <div class="links">
                <a href="{pubmed_url}" target="_blank" class="link">📄 PubMed</a>
"""
        
        if doi:
            html_content += f'                <a href="https://doi.org/{doi}" target="_blank" class="link">🔗 DOI</a>\n'
        
        html_content += f"""                <a href="#" onclick="toggleAbstract({i}); return false;" class="link">📖 Abstract</a>
            </div>
            <div class="abstract" id="abstract-{i}">
                <strong>Abstract:</strong><br>
                {abstract}
            </div>
        </div>
"""
    
    html_content += """
    </div>
    
    <script>
        function toggleAbstract(id) {
            const abstract = document.getElementById('abstract-' + id);
            abstract.classList.toggle('show');
        }
        
        function sortPublications() {
            const sortBy = document.getElementById('sortBy').value;
            const container = document.getElementById('publications');
            const pubs = Array.from(container.getElementsByClassName('publication'));
            
            pubs.sort((a, b) => {
                let aVal, bVal;
                
                if (sortBy === 'year') {
                    aVal = parseInt(a.getAttribute('data-year')) || 0;
                    bVal = parseInt(b.getAttribute('data-year')) || 0;
                    return bVal - aVal; // Newest first
                } else if (sortBy === 'citations') {
                    aVal = parseInt(a.getAttribute('data-citations')) || 0;
                    bVal = parseInt(b.getAttribute('data-citations')) || 0;
                    return bVal - aVal; // Most cited first
                } else if (sortBy === 'rcr') {
                    aVal = parseFloat(a.getAttribute('data-rcr')) || 0;
                    bVal = parseFloat(b.getAttribute('data-rcr')) || 0;
                    return bVal - aVal; // Highest RCR first
                }
                return 0;
            });
            
            // Clear and re-append in sorted order
            container.innerHTML = '';
            pubs.forEach(pub => container.appendChild(pub));
        }

        // Default to sort by RCR on load
        window.addEventListener('DOMContentLoaded', () => {
            document.getElementById('sortBy').value = 'rcr';
            sortPublications();
        });
    </script>
</body>
</html>
"""
    
    return html_content


def create_html_output(publications, filename, author_name):
    """Write HTML content for publications to a file."""
    html_content = build_html_content(publications, author_name)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)



def main():
    parser = argparse.ArgumentParser(
        description='Fetch all publications for an author from PubMed',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch_author_publications.py "Knowles DA" your@email.com
  python fetch_author_publications.py "Smith J" your@email.com --start-year 2020
  python fetch_author_publications.py "Doe J" your@email.com --format json
  python fetch_author_publications.py "Brown AB" your@email.com --start-year 2015 --end-year 2023
        """
    )
    
    parser.add_argument('author', help='Author name (e.g., "Knowles DA" or "Smith J")')
    parser.add_argument('--email', default="knowles84@gmail.com", help='Your email address (required by NCBI)')
    parser.add_argument('--start-year', type=int, help='Start year for filtering publications')
    parser.add_argument('--end-year', type=int, help='End year for filtering publications')
    parser.add_argument('--format', choices=['csv', 'json', 'html', 'both'], default='html', help='Output format (default: html)')
    
    args = parser.parse_args()
    
    # Fetch publications
    publications = fetch_author_publications(
        author_name=args.author,
        email=args.email,
        start_year=args.start_year,
        end_year=args.end_year,
        output_format=args.format
    )
    
    if publications:
        # Save to file
        save_publications(publications, args.author, args.format)
        
        # Print summary
        print(f"\nSummary:")
        print(f"Total publications: {len(publications)}")
        years = [p.get("Year", "") for p in publications if p.get("Year")]
        if years:
            print(f"Year range: {min(years)} - {max(years)}")
    else:
        print("No publications found.")


if __name__ == "__main__":
    main()
