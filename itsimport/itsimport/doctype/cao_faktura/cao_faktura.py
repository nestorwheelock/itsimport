# -*- coding: utf-8 -*-
# Copyright (c) 2017, itsdave GmbH and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.database import Database
from time import sleep
import MySQLdb as mdb
import sys
reload(sys)
sys.setdefaultencoding('utf-8')

class CAOFaktura(Document):
    def runCaoImport(self):
        frappe.msgprint("Import aus Datenbank " + self.cao_datenbank)
        caodb = frappe.database.Database(host=self.cao_datenbankserver, user=self.cao_user, password = self.cao_passwort)
        caodb.begin()
        caodb.use(self.cao_datenbank)
        caoAddresses = caodb.sql("Select ANREDE, KUNNUM1, NAME1, NAME2, NAME3, STRASSE, PLZ, ORT, LAND from adressen where KUNNUM1 <>'';", as_dict=1)
        #Statistikzähler initialisieren
        count_customerTotal = 0
        count_customerInserted = 0
        count_customerUpdated = 0
        count_customerSkipped = 0
        count_addressInserted = 0
        count_addressUpdated = 0
        count_addressSkipped = 0
        #Wir verarbeiten alle CAO Adressen zu ERPNext Customer
        for caoAddress in caoAddresses:
            count_customerTotal += 1
            #Wir legen fest, wie der Datensatz heißen soll
            currentCustomerName = 'CUST-' + caoAddress['KUNNUM1']
            #Danach verarbeiten wir den Datensatz: Zunächst erzeugen wir aus jeder CAO Adresse einen ERPNext Customer (oder aktualiseren)
            customerReturn = self.compareUpdateOrInsertCustomer(caoAddress, currentCustomerName)
            if customerReturn == 'inserted': count_customerInserted += 1
            if customerReturn == 'updated': count_customerInserted += 1
            if customerReturn == 'skipped': count_customerSkipped += 1
            #anschließend wird auch eine ERPNext Adresse erzeugt und verknüpft (oder aktualisert)
            addressReturn = self.compareUpdateOrInsertAddress(caoAddress, currentCustomerName)
            if addressReturn == 'inserted': count_addressInserted += 1
            if addressReturn == 'updated': count_addressInserted += 1
            if addressReturn == 'skipped': count_addressSkipped += 1

        #Statistik ausgeben
        frappe.msgprint("Es wurden " + str(count_customerTotal) + " CAO Adresen (ERPNext Customer) verarbeitet.")
        if count_customerInserted > 0:
            frappe.msgprint(str(count_customerInserted) + " Customer eingefügt.")
        if count_customerUpdated > 0:
            frappe.msgprint(str(count_customerUpdated) + " Customer aktualisiert.")
        if count_customerSkipped > 0:
            frappe.msgprint(str(count_customerSkipped) + " Customer waren bereits aktuell.")

    def compareUpdateOrInsertCustomer(self, caoAddress, currentCustomerName):
        print("processing " + currentCustomerName)
        #Wenn es bereits einen Kunden mit der Kundenummer gibt, laden wir den Datensatz
        if frappe.get_all('Customer', {"name": currentCustomerName }):
            customerDoc = frappe.get_doc('Customer',currentCustomerName)
            #Wenn es bereits einen Kunden mit der Kundenummer gibt, vergleichen wir die Felder
            changeDetected = False
            if not customerDoc.customer_name == self.assembleCustomerName(caoAddress):
                changeDetected = True
                print(type(customerDoc.customer_name))
                print(type(self.assembleCustomerName(caoAddress)))
                customerDoc.customer_name = self.assembleCustomerName(caoAddress)
                frappe.msgprint(customerDoc.customer_name)
                frappe.msgprint(self.assembleCustomerName(caoAddress))
            if changeDetected:
                print("updating " + currentCustomerName)
                customerDoc.save()
                return 'updated'
            else:
                print("allready up to date " + currentCustomerName)
                return 'skipped'
        #Wenn es noch keinen Kunden mit der Kundenummer gibt, legen wir ihn an:
        else:
            customerDoc = frappe.get_doc({"doctype":"Customer",
                                          "naming_series":currentCustomerName,
                                          "customer_type":"Company",
                                          "do_not_autoname":True,
                                          "territory":"Germany",
                                          "customer_group":"kommerziell",
                                          "customer_name":self.assembleCustomerName(caoAddress)})
            print("inserting " + currentCustomerName)
            customerDoc.insert()
            return 'inserted'


    def compareUpdateOrInsertAddress(self, caoAddress, currentCustomerName):
        insertAddressName = currentCustomerName + '-CAO' #zu erkennung, woher die Adresse kommt
        expectedAddressName = insertAddressName + '-Abrechnung' #da ERPNext beim Einfügen die Übersetzung des Adresstyps anhängt
        if frappe.get_all('Address', {"name": expectedAddressName}):
            frappe.msgprint('Adresse ' + expectedAddressName + 'bereits vorhanden')
            return 'skipped'
        else:
            frappe.msgprint('Adresse ' + expectedAddressName + ' nicht vorhanden')
            addressDoc = frappe.get_doc({"doctype":"Address",
                                          "name": insertAddressName,
                                          "address_title": insertAddressName,
                                          "address_type":"Billing",
                                          "address_line1":caoAddress['STRASSE'],
                                          "pincode":caoAddress['PLZ'],
                                          "city":caoAddress['ORT'],
                                          "country":'Germany'})
            print("inserting address " + insertAddressName)
            try:
                addressDoc.insert()
                addressLink = frappe.get_doc({"doctype":"Dynamic Link",
                                              "link_doctype": "Customer",
                                              "link_name": currentCustomerName,
                                              "parent": expectedAddressName,
                                              "parentfield": 'links',
                                              "parenttype": "Address" })
                try:
                    addressLink.insert()
                    return 'inserted'
                except Exception as e:
                    pass

            except Exception as e:
                pass


    def compareUpdateOrInsertContact(self, Address):
        pass

    def assembleCustomerName(self, caoAddress):
        #Namen zusammensetzen, falls Namensfelder leer, CAO Kunde und Kundennummer verwenden
        customer_name_new = None
        if caoAddress['NAME1'] is not None:
            customer_name_new = caoAddress['NAME1'].strip()
        if caoAddress['NAME2'] is not None:
            if customer_name_new:
                customer_name_new = customer_name_new + ' ' + caoAddress['NAME2'].strip()
        if caoAddress['NAME3'] is not None:
            if customer_name_new:
                customer_name_new = customer_name_new + ' ' + caoAddress['NAME3'].strip()
        if not customer_name_new:
            customer_name_new = 'CAO Kunde ' + caoAddress['KUNNUM1'].strip()
        return customer_name_new

    def create_item(self, item_data):

        item_code = "CAO-" + item_data["map_id"]
        found_items = frappe.get_all("Item", filters={"item_code": item_code }, fields=["name", "item_code"] )
        if len(found_items) >= 1:
            print "Item " + item_code + " allready exists."

        else:
            item_doc = frappe.get_doc({"doctype": "Item",
            "item_code": item_code,
            "item_group": self.destination_articlegroup,
            "item_name": item_data["desc_short"],
            "is_stock_item": item_data["is_stock_item"],
            "standard_rate": item_data["standard_rate"],
            "opening_stock": item_data["opening_stock"]
            })
            item = item_doc.insert()
            if item == "vggr":
                stock_entry_detail = frappe.get_doc({   "doctype": "Stock Entry Detail",
                                                        "t_warehouse": self.t_warehouse,
                                                        "item_code": item_code,
                                                        "qty": item_data["opening_stock"]})

                stock_entry = frappe.get_doc({"doctype": "Stock Entry",
                                        #"name" : "CAO-Import-Mengenübernahme",
                                        "purpose": "Material Receipt"

                                        })
                stock_entry.append("items", stock_entry_detail)
                ste_name = stock_entry.insert().name

                print ste_name

                STE = frappe.get_doc("Stock Entry", ste_name)

                STE.submit()


    def runArticleImport(self):
        con = mdb.connect(self.cao_datenbankserver, self.cao_user, self.cao_passwort, self.cao_datenbank)
        sql = (   "select ARTNUM, WARENGRUPPE, KURZNAME, LANGNAME, EK_PREIS, VK5, MENGE_AKT "
                                    "from artikel "
                                    "where MENGE_AKT > 0;")
        cur = con.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        items = []
        for row in rows:
            item = {"map_id": str(row[0]).decode('iso-8859-1').encode('utf-8')[:140],
                    "desc_short": str(row[2]).decode('iso-8859-1').encode('utf-8')[:140],
                    "standard_rate": row[5],
                    "is_stock_item": True,
                    "opening_stock": row[6]}
            self.create_item(item)
