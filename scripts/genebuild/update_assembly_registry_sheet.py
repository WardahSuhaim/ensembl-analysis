# Copyright [2018] EMBL-European Bioinformatics Institute
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mysql.connector
from mysql.connector import Error
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pprint
import unicodedata
import time
import datetime
import argparse
#import traceback

def fetch_db_data(query,database,host,port,user,password):
  try:
    conn = mysql.connector.connect(database=database,
                                   host=host,
                                   port=port,
                                   user=user,
                                   password=password)

    cursor = conn.cursor()
    cursor.execute(query)
 
    rows = cursor.fetchall()
 
  except Error as e:
      print(e)
 
  finally:
    cursor.close()
    conn.close()

  return rows


def update_assembly_sheet(assembly_db_data,meta_db_data,existing_sheet_records,assembly_sheet,gettime,worksheet_name):
  # This method creates a dictionary for both the lists from the db and sheets and makes both
  # dicts key on the versioned GCA (which is unique). Once the dicts are generated keys in the
  # assembly db dict are compared to the keys in the sheets dict. If a key is not in the sheets
  # dict then it is a new entry and gets made into a new row and added to the sheet. If the key
  # is present then some tests are done to see of anything needs updating. Some of these tests
  # could be made generic, but there are some complex cases like when the filters need updating
  # The filters are basically tags for the assemblies that are then used to create the filter
  # views in sheets
  min_contig_n50_filter = 30000
  assembly_db_dict = {}
  existing_sheet_dict = {}
  max_version_dict = {}
  existing_annotations_dict = {}

  # This ordering needs to match the ordering of the query on the assembly db 
  assembly_db_columns = ['species_name','common_name','chain','version','clade','contig_N50','assembly_level','assembly_date','refseq_accession','assembly_name','genome_rep']

  # This ordering needs to match the ordering of the columns on the sheet
  assembly_sheet_columns = ['GCA','Clade','Species name','Common name','Contig N50','Assembly level','Assembly date','Assembly name','RefSeq accession','Genebuilder','Status',
                            'Expected release','Grant','Notes','Filter: Max version','Filter: Genome rep','Filter: N50','Filter: Non-human']
   
  # This makes a dict for the db on the versioned GCA and also makes a dict to track the highest
  # version for a particular GCA (used in filtering later)
  # Note the db has entries are in unicode in some cases and need to be converted
  for row in assembly_db_data:
    chain = row[assembly_db_columns.index('chain')]
    version = row[assembly_db_columns.index('version')]
    chain.encode('ascii','ignore')
    gca = make_gca(chain,version)

    assembly_db_dict[gca] = row
    if chain in max_version_dict:
      current_max_version = max_version_dict[chain]
      if version > current_max_version:
        max_version_dict[chain] = version
    else:
      max_version_dict[chain] = version

  # This makes an existing annotations dict based on the meta data db. Note that this db only
  # goes back to e80, so there is a small chance that assemblies were once annotated are not marked
  # as handed over in the filters, but this shouldn't be a problem
  for row in meta_db_data:
    gca = row[0]
    gca.encode('ascii','ignore')
    existing_annotations_dict[gca] = 1

  # This just makes a dict for the sheet based on the versioned GCA
  for row in existing_sheet_records:
    gca = row[0]
    gca.encode('ascii','ignore')

    if(gca == 'GCA'):
      next
    else:
      existing_sheet_dict[gca] = row
 

  # This is where the majority of the work occurs. All assembly GCAs are examined to determined what
  # should be added/updated
  # Note that currently a three second sleep is need to avoid exhausting the Sheets REST API quota
  for gca in assembly_db_dict:
    #Check that time since last authentication is < 1hr
    if(time.time() - gettime > 60* 59):#If greater than 1 hr, then re-authenticate
        print("Updating time: " + gca)
         # use creds to create a client to interact with the Google Drive API
        scope = ['https://spreadsheets.google.com/feeds',
           'https://www.googleapis.com/auth/drive']

        creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
        client = gspread.authorize(creds)
        gettime = time.time()
     # Find a workbook by name and open the first sheet
     # Make sure you use the right name here.
        assembly_sheet = client.open(worksheet_name).sheet1
        #response = client.login()
        #if response:
          #  print ("Success line ")
          #  print (response)
           # return response
        #else:
         #   print ("Error line ")
          #  print(response)
       # gettime = time.time()#Get time of re-authentication
    assembly_row = assembly_db_dict[gca]
    species_name = assembly_row[assembly_db_columns.index('species_name')]
    common_name = assembly_row[assembly_db_columns.index('common_name')]
    chain = assembly_row[assembly_db_columns.index('chain')]
    chain.encode('ascii','ignore')
    version = assembly_row[assembly_db_columns.index('version')]
    clade = assembly_row[assembly_db_columns.index('clade')]
    contig_N50 = assembly_row[assembly_db_columns.index('contig_N50')]
    assembly_level = assembly_row[assembly_db_columns.index('assembly_level')]
    assembly_date = assembly_row[assembly_db_columns.index('assembly_date')]
    refseq_accession = assembly_row[assembly_db_columns.index('refseq_accession')]
    assembly_name = assembly_row[assembly_db_columns.index('assembly_name')]
    genome_rep = assembly_row[assembly_db_columns.index('genome_rep')]
    gca = make_gca(chain,version)
    annotation_status = 'Not started'
    if gca in existing_annotations_dict:
      annotation_status = 'Handed over'

    # If the row does not exist then add it in with the filtering info
    if not gca in existing_sheet_dict:
      new_row = [gca,clade,species_name,common_name,contig_N50,assembly_level,assembly_date.strftime('%Y-%m-%d'),assembly_name,refseq_accession,'Not assigned',annotation_status,'','Not assigned','']

      # This section sets various filters
      if version == max_version_dict[chain]:
        new_row.append(1)
      else:
        new_row.append(0)

      if genome_rep == 'full':
        new_row.append(1)
      else:
        new_row.append(0)
     
      if contig_N50 >= min_contig_n50_filter:
        new_row.append(1)
      else:
        new_row.append(0)

      # There is an issue with the db at the moment with trailing spaces on the species names, but this should get fixed
      if not (species_name == "Homo sapiens " or species_name == "Homo sapiens"):
        new_row.append(1)
      else:
        new_row.append(0)

      print(new_row)
      insert_index = 2
      assembly_sheet.append_row(new_row)
      time.sleep(3)

    # If it does exist we need to check if an update is required. There are only a few columns this might pertain to
    else:
      sheet_row = existing_sheet_dict[gca]
      sheet_clade_index = assembly_sheet_columns.index('Clade')
      sheet_clade_val = sheet_row[sheet_clade_index]
      sheet_filter_version_index = assembly_sheet_columns.index('Filter: Max version')
      sheet_filter_N50_index = assembly_sheet_columns.index('Filter: N50')
      sheet_filter_version_val = sheet_row[sheet_filter_version_index]
      sheet_filter_N50_val = sheet_row[sheet_filter_N50_index]
      sheet_refseq_accession_index = assembly_sheet_columns.index('RefSeq accession')
      sheet_assembly_name_index = assembly_sheet_columns.index('Assembly name')
      sheet_refseq_accession_val = sheet_row[sheet_refseq_accession_index]
      sheet_assembly_name_val = sheet_row[sheet_assembly_name_index]

      if clade != sheet_clade_val:
        # Update the classification
        print("Updating the clade for: " + gca)
        row_update_index = assembly_sheet.find(gca).row
        update_cell_val(assembly_sheet,row_update_index,sheet_clade_index,clade)
        time.sleep(3)

      if sheet_filter_version_val == "1" and str(version) != str(max_version_dict[chain]):
        # update the max version to 0
        print("Updating max version filter val for: " + gca)
        row_update_index = assembly_sheet.find(gca).row
        update_cell_val(assembly_sheet,row_update_index,sheet_filter_version_index,0)
        time.sleep(3)


      if contig_N50 >= min_contig_n50_filter and sheet_filter_N50_val == "0":
        # update the N50 filter to 1
        print("Updating contig_N50 filter val to 1 for: " + gca)
        row_update_index = assembly_sheet.find(gca).row
        update_cell_val(assembly_sheet,row_update_index,sheet_filter_N50_index,1)
        time.sleep(3)
      elif (contig_N50 < min_contig_n50_filter) and (sheet_filter_N50_val == "1"): 
        # update the N50 filter to 0
        print("Updating contig_N50 filter val to 0 for: " + gca)
        row_update_index = assembly_sheet.find(gca).row
        update_cell_val(assembly_sheet,row_update_index,sheet_filter_N50_index,0)
        time.sleep(3)


      if not refseq_accession is None and refseq_accession != sheet_refseq_accession_val:
        # Add/update the RefSeq accession
        print("Updating RefSeq accession for: " + gca)
        row_update_index = assembly_sheet.find(gca).row
        update_cell_val(assembly_sheet,row_update_index,sheet_refseq_accession_index,refseq_accession)
        time.sleep(3)

      if not assembly_name is None and assembly_name != sheet_assembly_name_val:
        # Add/update the RefSeq accession
        print("Updating Assembly name for: " + gca)
        row_update_index = assembly_sheet.find(gca).row
        update_cell_val(assembly_sheet,row_update_index,sheet_assembly_name_index,assembly_name)
        time.sleep(3)
      
def make_gca(chain,version):
  gca = chain + '.' + str(version)
  return gca


def update_cell_val(assembly_sheet,row_index,col_offset,val):
  col_offset += 1
  assembly_sheet.update_cell(row_index,col_offset,val)

   
if __name__ == '__main__':

  parser = argparse.ArgumentParser()
  parser.add_argument('-ad','--assembly_db_dbname', help='Name for assembly registry db', required=True)
  parser.add_argument('-ah','--assembly_db_host', help='Host for assembly registry db', required=True)
  parser.add_argument('-ap','--assembly_db_port', help='Port for assembly registry db', required=True)
  parser.add_argument('-au','--assembly_db_user', help='User for assembly registry db', required=True)

  parser.add_argument('-md','--meta_db_dbname', help='Name for meta data db', required=True)
  parser.add_argument('-mh','--meta_db_host', help='Host for meta data db', required=True)
  parser.add_argument('-mp','--meta_db_port', help='Port for meta data db', required=True)
  parser.add_argument('-mu','--meta_db_user', help='User for meta data db', required=True)

  parser.add_argument('-wsn','--worksheet_name', help='The name of the Google Sheets worksheet', required=True)
  parser.add_argument('-gsc','--gsheets_credentials', help='Path to a Google Sheets credentials JSON file for authentication', required=True)
  args = parser.parse_args()
  assembly_db_query = 'SELECT species_name,common_name,chain,version,clade,contig_N50,assembly_level,assembly_date,refseq_accession,assembly_name,genome_rep FROM assembly JOIN meta USING(assembly_id) JOIN species_space_log using(species_id)'
  assembly_db_database = args.assembly_db_dbname
  assembly_db_host = args.assembly_db_host
  assembly_db_port = args.assembly_db_port
  assembly_db_user = args.assembly_db_user
  assembly_db_password = ''
  assembly_db_data = fetch_db_data(assembly_db_query,assembly_db_database,assembly_db_host,assembly_db_port,assembly_db_user,assembly_db_password)

  meta_db_query = 'SELECT assembly_accession from assembly where assembly_accession like "GCA%"'
  meta_db_database = args.meta_db_dbname
  meta_db_host = args.meta_db_host
  meta_db_port = args.meta_db_port
  meta_db_user = args.meta_db_user
  meta_db_password = ''
  meta_db_data = fetch_db_data(meta_db_query,meta_db_database,meta_db_host,meta_db_port,meta_db_user,meta_db_password)

  worksheet_name = args.worksheet_name
  credentials_path = args.gsheets_credentials

  # use creds to create a client to interact with the Google Drive API
  scope = ['https://spreadsheets.google.com/feeds',
           'https://www.googleapis.com/auth/drive']

  creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
  #try:
  client = gspread.authorize(creds)
     #get 
  gettime = time.time()
     # Find a workbook by name and open the first sheet
     # Make sure you use the right name here.
  assembly_sheet = client.open(worksheet_name).sheet1

     # Extract and print all of the values
  existing_sheet_records = assembly_sheet.get_all_values()

     #Check if access token has expired
    # if creds.access_token_expired:
        #re-authenticate
  #      client.login() 
  update_assembly_sheet(assembly_db_data,meta_db_data,existing_sheet_records,assembly_sheet,gettime,worksheet_name)
#  except Exception, e:
 #    traceback.print_exc()
