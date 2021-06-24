from math import sin, cos, sqrt, atan2, radians
from matplotlib.colors import Normalize

import os
import json
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import sys


class Analyzer:
    """
    Class responsible for encapsulating all analysis functionality
    """

    # Measure unit conversion values

    @staticmethod
    def convert(input, conversion_multiplier):
        """
        Applies conversion multiplier to the input
        If input is list, returns a list with each input element multiplied
        If input is variable, returns multipled value
        """
        if type(input) == list:
            return list(map(lambda x: x * conversion_multiplier, input))
        else:
            return input * conversion_multiplier

    @staticmethod
    def mps_to_kmh(input):
        """
        Converts input in meters per second to kilometers per hour
        """
        return Analyzer.convert(input, 60.0 * 60.0 / 1000.0)

    @staticmethod
    def ms_to_s(input):
        """
        Converts input in milliseconds to seconds
        """
        return Analyzer.convert(input, 1.0 / 1000.0)

    @staticmethod
    def s_to_min(input):
        """
        Converts input in seconds to minutes
        """
        return Analyzer.convert(input, 1.0 / 60.0)

    @staticmethod
    def geo_to_meters(geoloc1, geoloc2):
        """
        Return the distance between two geo locations given as
        geoloc = [longitude, latitude]
        in meters
        """

        # Approximate radius of earth in meters
        R = 6373000.0

        lat1 = radians(geoloc1[1])
        lon1 = radians(geoloc1[0])
        lat2 = radians(geoloc2[1])
        lon2 = radians(geoloc2[0])

        dlon = lon2 - lon1
        dlat = lat2 - lat1

        a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        distance = R * c

        return distance

    def __init__(self, geojson_file, out_directory, batch_size=4, verbose=True):
        """
        Declares all needed values
        """
        # Store required parameters
        self.geojson_file = geojson_file
        self.out_directory = out_directory

        # Store optional parameters
        self.batch_size = batch_size
        self.verbose = verbose

        # Declare frame variables
        self.frame_data = {}
        self.frame_times_s = []
        self.num_frames = 0

        # Declare batch variables
        self.batch_times_s = []
        self.batch_dists_m = []
        self.batch_geo_locations = []
        self.batch_speeds_kmh = []
        self.accumulated_batch_times_s = []
        self.num_batches = 0

        # Declare lap variables
        self.lap_batches = []
        self.num_detected_laps = 0
        self.lap_average_speed_kmh = []

    def load_data_and_generate_graphs(self):
        """
        Function that loads data from the given file and manages all analysis steps
        """
        # Create output directory
        if not os.path.isdir(self.out_directory):
            os.mkdir(self.out_directory)

        # Load and digest original per frame data
        self.__prepare_frame_data()

        # Generate batch data by grouping frames
        self.__generate_batch_data()

        # Correct outlier speeds
        self.__correct_outlier_data()

        # Trim non-driving part at the beginning and the ending of the recorded data
        self.__trim_non_driving()

        # Detect laps
        self.__detect_laps()

        # Draw speed plot
        self.__plot_speed_time_graph()

        # Draw lap trajectory plots
        self.__plot_lap_trajectories()

    def __prepare_frame_data(self):
        """
        Loads per frame data from the file
        Converts Unix time to seconds
        Trims the back of the data array to make its length divisible by the batch size
        """
        if self.verbose:
            print()
            print('__prepare_frame_data')

        # Read geo data consisting of frames
        with open(self.geojson_file, 'r') as fin:
            self.frame_data = json.loads(fin.read())

        # Preview data
        if self.verbose:
            print('data.keys:', self.frame_data.keys())
            print('data.type:', self.frame_data['type'])
            print('data.geometry.keys:', self.frame_data['geometry'].keys())
            print('data.geometry.type:', self.frame_data['geometry']['type'])
            print('data.geometry.coordinates:', self.frame_data['geometry']['coordinates'][:10])
            print('data.properties:', self.frame_data['properties'].keys())
            print('data.properties.device:', self.frame_data['properties']['device'])
            print('data.properties.AbsoluteUtcMicroSec:', self.frame_data['properties']['AbsoluteUtcMicroSec'][:10])
            print('data.properties.RelativeMicroSec:', self.frame_data['properties']['RelativeMicroSec'][:10])

        # Convert time data to seconds
        self.frame_times_s = Analyzer.ms_to_s(self.frame_data['properties']['RelativeMicroSec'])

        if self.verbose:
            print('num frames loaded:', len(self.frame_times_s))
            print('total recording time s:', self.frame_times_s[-1])
            print('average frames per second:', len(self.frame_times_s) / self.frame_times_s[-1])

    def __generate_batch_data(self):
        """
        Groups frames into batches
        Calculates time, distance and speed values for each batch
        """
        if self.verbose:
            print()
            print('__generate_batch_data')

        # Round number of frames to be divisible by the batch size
        self.num_frames = ((len(self.frame_times_s) - 1) // self.batch_size) * self.batch_size
        self.frame_times_s = self.frame_times_s[:self.num_frames + 1]

        if self.verbose:
            print('num frames left after batch size trim:', self.num_frames)

        # Batch duration times in seconds
        self.batch_times_s = []
        # Batch distances in meters
        self.batch_dists_m = []
        # Batch initial geo location
        self.batch_geo_locations = []
        # Batch speeds in km/h
        self.batch_speeds_kmh = []

        # Group frames into batches with parameterized size and calculate speeds
        for i in range(0, self.num_frames, self.batch_size):
            time_s = self.frame_times_s[i + self.batch_size] - self.frame_times_s[i]
            self.batch_times_s.append(time_s)
            dist_m = 0
            for j in range(0, self.batch_size):
                dist_m += Analyzer.geo_to_meters(
                    self.frame_data['geometry']['coordinates'][i + j],
                    self.frame_data['geometry']['coordinates'][i + j + 1])
            self.batch_dists_m.append(dist_m)
            # Get average geolocation from the batch
            avg = lambda values: sum(values) / len(values)
            self.batch_geo_locations.append(
                list(map(avg, zip(*self.frame_data['geometry']['coordinates'][i:i + self.batch_size]))))
            self.batch_speeds_kmh.append(Analyzer.mps_to_kmh(dist_m / time_s))
        self.num_batches = len(self.batch_speeds_kmh)
        self.accumulated_batch_times_s = [sum(self.batch_times_s[:i + 1]) for i in range(self.num_batches)]

        if self.verbose:
            print('num batches:', self.num_batches)

    def __correct_outlier_data(self):
        """
        Check for inconsistencies in batch data and fix them up
        """
        if self.verbose:
            print()
            print('__correct_outlier_data')

        max_possible_speed_discrepancy_kmh = 7.0
        num_batches_speed_corrected = 0

        for spike_start_batch in range(1, self.num_batches - 1):
            for spike_batch_width in range(1, 5):
                if spike_start_batch < self.num_batches - spike_batch_width:
                    spike_detected = abs(self.batch_speeds_kmh[spike_start_batch - 1] - self.batch_speeds_kmh[spike_start_batch + spike_batch_width]) < max_possible_speed_discrepancy_kmh
                    for i in range(spike_batch_width):
                        spike_detected = spike_detected and (abs(self.batch_speeds_kmh[spike_start_batch - 1] - self.batch_speeds_kmh[spike_start_batch + i]) > max_possible_speed_discrepancy_kmh)
                    if spike_detected:
                        for i in range(spike_batch_width):
                            self.batch_speeds_kmh[spike_start_batch + i] = (self.batch_speeds_kmh[spike_start_batch - 1] * (spike_batch_width - i) + self.batch_speeds_kmh[spike_start_batch + spike_batch_width] * (1 + i)) / (spike_batch_width + 1)
                        num_batches_speed_corrected += spike_batch_width

        if self.verbose:
            print('num batches speed corrected:', num_batches_speed_corrected)

    def __trim_non_driving(self):
        """
        Trims batches with speed below the preset minimal driving speed
        from the beginning and the ending of the data arrays
        """
        if self.verbose:
            print()
            print('__trim_non_driving')

        min_driving_speed_kmh = 10.0

        drive_start_batch = 0
        while self.batch_speeds_kmh[drive_start_batch] < min_driving_speed_kmh:
            drive_start_batch += 1
        drive_end_batch = self.num_batches - 1
        while self.batch_speeds_kmh[drive_end_batch] < min_driving_speed_kmh:
            drive_end_batch -= 1

        if self.verbose:
            print('driving starts at min:', Analyzer.s_to_min(sum(self.batch_times_s[:drive_start_batch])))
            print('driving ends at min:', Analyzer.s_to_min(sum(self.batch_times_s[:drive_end_batch])))

        self.batch_times_s = self.batch_times_s[drive_start_batch:drive_end_batch]
        self.batch_dists_m = self.batch_dists_m[drive_start_batch:drive_end_batch]
        self.batch_geo_locations = self.batch_geo_locations[drive_start_batch:drive_end_batch]
        self.batch_speeds_kmh = self.batch_speeds_kmh[drive_start_batch:drive_end_batch]
        self.num_batches = len(self.batch_speeds_kmh)
        self.accumulated_batch_times_s = [sum(self.batch_times_s[:i]) for i in range(self.num_batches)]

        if self.verbose:
            print('num batches after trimming:', self.num_batches)
            print('total dist m:', sum(self.batch_dists_m))
            print('total time min:', Analyzer.s_to_min(sum(self.batch_times_s)))
            print('average speed km/h:', sum(self.batch_speeds_kmh) / self.num_batches)

    def __detect_laps(self):
        """
        Finds all batches with the position at the first point on the trajectory
        that has been visited more than once
        """
        if self.verbose:
            print()
            print('__detect_laps')

        min_possible_lap_time_s = 60.0
        lap_detection_min_distance_m = 10.0

        self.lap_batches = []
        curr_batch = next(x[0] for x in enumerate(self.accumulated_batch_times_s) if x[1] > min_possible_lap_time_s)
        while curr_batch < self.num_batches:
            if len(self.lap_batches) == 0:
                # No laps detected yet, check if the current batch completes the first lap
                possible_first_batch = 0
                while len(self.lap_batches) == 0 and \
                    self.accumulated_batch_times_s[possible_first_batch] + min_possible_lap_time_s < self.accumulated_batch_times_s[curr_batch]:
                        if Analyzer.geo_to_meters(
                            self.batch_geo_locations[possible_first_batch],
                            self.batch_geo_locations[curr_batch]) < lap_detection_min_distance_m:
                                self.lap_batches.append(possible_first_batch)
                                self.lap_batches.append(curr_batch)
                                curr_batch = next(x[0] for x in enumerate(self.accumulated_batch_times_s) if x[1] > self.accumulated_batch_times_s[curr_batch] + min_possible_lap_time_s)
                        possible_first_batch += 1
                if len(self.lap_batches) == 0:
                    curr_batch += 1
            else:
                # Not the first lap, check if current batch completes a later lap
                if Analyzer.geo_to_meters(
                    self.batch_geo_locations[self.lap_batches[1]],
                    self.batch_geo_locations[curr_batch]) < lap_detection_min_distance_m:
                        self.lap_batches.append(curr_batch)
                        curr_batch = next(
                            (x[0] for x in enumerate(self.accumulated_batch_times_s) if x[1] > self.accumulated_batch_times_s[curr_batch] + min_possible_lap_time_s),
                            self.num_batches)
                else:
                    curr_batch += 1
        self.num_detected_laps = len(self.lap_batches) - 1

        if self.verbose:
            print('num detected full laps:', self.num_detected_laps)

        # Calculate average speeds for each lap
        self.lap_average_speed_kmh = []
        for lap in range(self.num_detected_laps):
            self.lap_average_speed_kmh.append(Analyzer.mps_to_kmh(
                sum(self.batch_dists_m[self.lap_batches[lap]:self.lap_batches[lap + 1]]) / \
                (self.accumulated_batch_times_s[self.lap_batches[lap + 1]] - self.accumulated_batch_times_s[self.lap_batches[lap]])))

        if self.verbose:
            accumulated_batch_times_min = [x / 60.0 for x in self.accumulated_batch_times_s]
            print('lap #, time and avg speed')
            for i in range(self.num_detected_laps):
                print(i + 1, accumulated_batch_times_min[self.lap_batches[i + 1]] - accumulated_batch_times_min[self.lap_batches[i]], self.lap_average_speed_kmh[i])

    def __plot_speed_time_graph(self):
        """
        Draws speed over time graph containing
        - Speed [km/h] over time [min]
        - Vertical lines marking laps
        - Horizontal lines marking average speed for each lap
        """
        if self.verbose:
            print()
            print('__plot_speed_time_graph')

        accumulated_batch_times_min = Analyzer.s_to_min(self.accumulated_batch_times_s)
        lap_average_speed_kmh_graph = []
        for i in range(self.num_detected_laps):
            lap_average_speed_kmh_graph += [self.lap_average_speed_kmh[i] for _ in range(self.lap_batches[i + 1] - self.lap_batches[i])]
        fig, ax = plt.subplots(1, 1, figsize=(28, 7))
        ax.grid(axis='y', linestyle='--')
        ax.plot(accumulated_batch_times_min, self.batch_speeds_kmh, color='red', label='Speed')
        ax.plot(accumulated_batch_times_min[self.lap_batches[0]:self.lap_batches[-1]], lap_average_speed_kmh_graph, color='blue', label='Average speed per lap')
        for lap_batch in self.lap_batches:
            plt.axvline(x=accumulated_batch_times_min[lap_batch], color='gray', linestyle='--')
        ax.set_ylim((0, max(self.batch_speeds_kmh) * 1.1))
        ax.set_xlim((accumulated_batch_times_min[0], accumulated_batch_times_min[-1]))
        ax.set(
            xlabel='time (min)',
            ylabel='speed (km/h)',
            title='Driving speed')
        ax.set_xticks([x / 2.0 for x in range(int(max(accumulated_batch_times_min)) * 2 + 1)])
        ax.legend()
        fig.savefig(os.path.join(self.out_directory, 'driving_speed.png'), bbox_inches='tight')

    def __plot_lap_trajectories(self):
        """
        Draws trajectory contours for each lap,
        colored according to the current speed
        """
        if self.verbose:
            print()
            print('__plot_lap_trajectories')

        max_recorded_speed = max(self.batch_speeds_kmh)
        lats = [x[1] for x in self.batch_geo_locations]
        lons = [x[0] for x in self.batch_geo_locations]
        min_lat_batch = lats.index(min(lats))
        max_lat_batch = lats.index(max(lats))
        min_lon_batch = lons.index(min(lons))
        max_lon_batch = lons.index(max(lons))
        d_lat = Analyzer.geo_to_meters(
            [lats[min_lat_batch], lons[min_lat_batch]],
            [lats[max_lat_batch], lons[min_lat_batch]])
        d_lon = Analyzer.geo_to_meters(
            [lats[min_lon_batch], lons[min_lon_batch]],
            [lats[min_lon_batch], lons[max_lon_batch]])
        aspect_ratio = d_lat / d_lon
        fig, ax = plt.subplots(self.num_detected_laps, figsize=(11, 4 * self.num_detected_laps))
        for i in range(self.num_detected_laps):
            x_coords = [(x - min(lons)) / (max(lons) - min(lons)) for x in lons[self.lap_batches[i]:self.lap_batches[i + 1]]]
            y_coords = [(x - min(lats)) / (max(lats) - min(lats)) for x in lats[self.lap_batches[i]:self.lap_batches[i + 1]]]
            colors = cm.jet([x / max_recorded_speed for x in self.batch_speeds_kmh[self.lap_batches[i]:self.lap_batches[i + 1]]])
            ax[i].set_title('Lap %d' % (i + 1))
            ax[i].scatter(x_coords, y_coords, color=colors)
            ax[i].scatter(x_coords[0], y_coords[0], color='gray', s=70)
            ax[i].set_aspect(aspect_ratio)
            ax[i].get_xaxis().set_visible(False)
            ax[i].get_yaxis().set_visible(False)
        fig.subplots_adjust(top=0.95)
        title_ax = fig.add_axes([0.15, 0.95, 0.7, 0.03])
        title_ax.axis('off')
        title_ax.text(0.5, 0.8, 'Lap contours', ha='center', va='center', fontsize=20)
        fig.subplots_adjust(bottom=0.05)
        cbar_ax = fig.add_axes([0.2, 0.02, 0.6, 0.01])
        fig.colorbar(
            cm.ScalarMappable(norm=Normalize(0, max_recorded_speed), cmap=cm.jet),
            cax=cbar_ax,
            orientation='horizontal',
            ticks=[max_recorded_speed * i / 5 for i in range(6)],
            label='km/h')
        fig.savefig(os.path.join(self.out_directory, 'lap_contours.png'), bbox_inches='tight')


if __name__ == '__main__':

    # Check command line arguments
    if len(sys.argv) != 3:
        print('Usage: %s <geojson_file> <out_directory>' % os.path.basename(__file__))
        exit(1)

    analyzer = Analyzer(sys.argv[1], sys.argv[2])
    analyzer.load_data_and_generate_graphs()
