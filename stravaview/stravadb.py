#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import stravalib.client
import stravalib.unithelper
import pymysql.cursors
import pymysql.converters


def _escape_string(s):
    """
    Escape a string unless is None
    """
    if (s is not None):
        assert(isinstance(s, basestring))
        return pymysql.converters.escape_string(s)
    else:
        return s


class Strava:
    """
    Create a local Strava instance with its own local database containing only the funny rides (no commute).
    """
    FRAME_TYPES = {0: "none", 1: "mtb", 3: "road", 2: "cx", 4: "tt"}

    def __init__(self, config):
        """
        Initialize the StravaView class.

        Create a connection to the mysql server and prepare the dialog with the Strava api

        :param config:  a dictionnary as returned by readconfig.read_config
        """
        self.config = config
        self.connection = pymysql.connect(host='localhost', user=config['mysql_user'], password=config['mysql_password'], db=config['mysql_base'], charset='utf8')
        self.cursor = self.connection.cursor(pymysql.cursors.DictCursor)
        self.stravaClient = stravalib.Client(access_token=config['strava_token'])

    def close(self):
        self.cursor.close()
        self.connection.close()

    def create_bikes_table(self):
        """
        Create the bikes table if it does not already exist
        """
        # Check if table already exists
        table = self.config['mysql_bikes_table']
        sql = "SHOW TABLES LIKE '%s'" % table
        if (self.cursor.execute(sql) > 0):
            print("The table '%s' already exists" % table)
            return

        sql = """CREATE TABLE %s (
        id varchar(45) NOT NULL,
        name varchar(256) DEFAULT NULL,
        type enum('road','mtb','cx','tt') DEFAULT NULL,
        frame_type int(11) DEFAULT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY strid_UNIQUE (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8""" % table
        self.cursor.execute(sql)
        self.connection.commit()

    def create_activities_table(self):
        """
        Create the activities table if it does not already exist
        """
        # Check if table already exists
        table = self.config['mysql_activities_table']
        sql = "SHOW TABLES LIKE '%s'" % table
        if (self.cursor.execute(sql) > 0):
            print("The table '%s' already exists" % table)
            return

        sql = """CREATE TABLE %s (
        id int(11) NOT NULL,
        name varchar(256) DEFAULT NULL,
        location varchar(256) DEFAULT NULL,
        date datetime DEFAULT NULL,
        distance float DEFAULT 0,
        elevation float DEFAULT 0,
        moving_time time DEFAULT NULL,
        elapsed_time time DEFAULT NULL,
        gear_id varchar(45) DEFAULT NULL,
        average_speed float DEFAULT NULL,
        max_heartrate int DEFAULT NULL,
        average_heartrate float DEFAULT NULL,
        suffer_score int DEFAULT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY strid_UNIQUE (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8""" % table
        self.cursor.execute(sql)
        self.connection.commit()

    def update_bikes(self):
        """
        Update the bikes table
        """
        # Connect to the database
        table = self.config['mysql_bikes_table']
        bikes = self.stravaClient.get_athlete().bikes
        for bike in bikes:
            desc = self.stravaClient.get_gear(bike.id)

            # Check if the bike already exists
            sql = "SELECT * FROM %s WHERE id='%s' LIMIT 1" % (table, bike.id)
            if (self.cursor.execute(sql) > 0):
                continue

            sql = "INSERT INTO %s (id, name, type, frame_type) VALUES ('%s','%s', '%s', '%d')" % (table, desc.id, desc.name, self.FRAME_TYPES[desc.frame_type], desc.frame_type)
            self.cursor.execute(sql)
            self.connection.commit()

    def push_activity(self, activity):
        """
        Add the activity `activity` to the activities table

        :param activity: an object of class:`stravalib.model.Activity`
        """
        table = self.config['mysql_activities_table']
        # Check if activity is already in the table
        sql = "SELECT * FROM %s WHERE id='%s' LIMIT 1" % (table, activity.id)
        if (self.cursor.execute(sql) > 0):
            print("Activity '%s' already exists in table" % (activity.name))
            return

        if (activity.type != u'Ride' or activity.commute):
            print("Activity '%s' is not a pleasure ride" % (activity.name))
            return
        name = _escape_string(activity.name)
        if activity.distance is not None:
            distance = "%0.2f" % stravalib.unithelper.kilometers(activity.distance).get_num()
        else:
            distance = 0
        if activity.total_elevation_gain is not None:
            elevation = "%0.0f" % stravalib.unithelper.meters(activity.total_elevation_gain).get_num()
        else:
            elevation = 0
        date = activity.start_date_local
        location = _escape_string(activity.location_city)
        moving_time = activity.moving_time
        elapsed_time = activity.elapsed_time
        gear_id = _escape_string(activity.gear_id)
        if activity.average_speed is not None:
            average_speed = "%0.1f" % stravalib.unithelper.kilometers_per_hour(activity.average_speed).get_num()
        else:
            activity.average_speed = 0
        if activity.average_heartrate is not None:
            average_heartrate = "%0.0f" % activity.average_heartrate
        else:
            average_heartrate = 0
        max_heartrate = activity.max_heartrate
        suffer_score = activity.suffer_score

        sql = """INSERT INTO %s (id, name, distance, elevation, date, location, moving_time, elapsed_time,
        gear_id, average_speed, average_heartrate, max_heartrate, suffer_score)
        VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')
        """ % (table, activity.id, name, distance, elevation, date, location, moving_time, elapsed_time,
               gear_id, average_speed, average_heartrate, max_heartrate, suffer_score)
        self.cursor.execute(sql)
        self.connection.commit()

    def update_activities(self):
        """
        Update the activities table
        """
        table = self.config['mysql_activities_table']
        # Get the most recent activity
        sql = "SELECT date FROM %s ORDER BY date DESC LIMIT 1" % table
        if (self.cursor.execute(sql) == 0):
            after = None
        else:
            after = self.cursor.fetchone()['date']
        new_activities = self.stravaClient.get_activities(after=after)
        for activity in new_activities:
            self.push_activity(activity)

    def print_row(self, row):
        """
        Print a row retrieved from the activities table

        :param row: a result from a SQL fetch function
        :type row: a ditcionnary
        """
        name = row['name'].encode('utf-8')
        identifier = row['id']
        date = row['date'].date()
        distance = row['distance']
        elevation = row['elevation']
        elapsed_time = row['elapsed_time']
        moving_time = row['moving_time']
        print ("{7}: {1} | {2} | {3} | {4} | {5} | {6} | https://www.strava.com/activities/{0}".format(identifier, name, date, distance, elevation, moving_time, elapsed_time, row['type']))

    def get_activities(self, before=None, after=None, name=None, biketype=None):
        """
        Get all the activities matching the criterions

        :param before: lower-bound on the date of the activity
        :type before: str or datetime.date or datetime.datetime

        :param after: upper-bound on the date of the activity
        :type after: str or datetime.date or datetime.datetime

        :param name: a substring of the activity name
        :type name: str

        :param category: the type of bike used
        :type category: an element from FRAME_TYPES {'mtb', 'road', 'cx', 'tt'}
        """

        before_sql = ""
        after_sql = ""
        name_sql = ""
        conds = list()
        if before is not None:
            before_sql = "a.date <= '%s'" % before
            conds.append(before_sql)

        if after is not None:
            after_sql = "a.date >= '%s'" % after
            conds.append(after_sql)

        if name is not None:
            name_sql = "a.name LIKE '%%%s%%'" % _escape_string(name)
            conds.append(name_sql)

        if biketype is not None:
            if not (biketype in self.FRAME_TYPES.values()):
                print("{0} is not valid. Use {1}, {2}, {3}, {4}".format(biketype, self.FRAME_TYPES[1], self.FRAME_TYPES[2], self.FRAME_TYPES[3], self.FRAME_TYPES[4]))
                biketype = None
            else:
                biketype_sql = "b.type = '%s'" % biketype
                conds.append(biketype_sql)

        sql = "SELECT a.*, b.type FROM %s AS a INNER JOIN %s AS b ON a.gear_id = b.id" % (self.config['mysql_activities_table'], self.config['mysql_bikes_table'])
        if len(conds) > 0:
            where = " AND ".join(conds)
            sql = sql + " WHERE " + where
        sql = sql + " ORDER BY date DESC"
        print(sql + "\n")
        self.cursor.execute(sql)
        for row in self.cursor.fetchall():
            self.print_row(row)
