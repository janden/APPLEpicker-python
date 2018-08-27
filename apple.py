#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jun 19 09:40:13 2018

@author: Ayelet Heimowitz, Itay Sason
"""
import argparse
import glob
import numpy as np
import os

from functools import partial
from multiprocessing import Pool

from exceptions import ConfigError
from picking import Picker
from config import ApplePickerConfig


class Apple(object):

    def __init__(self, config, mrc_dir):

        self.particle_size = config.particle_size
        self.query_image_size = config.query_image_size
        self.query_window_size = config.query_window_size
        self.max_particle_size = config.max_particle_size
        self.min_particle_size = config.min_particle_size
        self.minimum_overlap_amount = config.minimum_overlap_amount
        self.tau1 = config.tau1
        self.tau2 = config.tau2
        self.container_size = config.container_size
        self.proc = config.proc
        self.output_dir = config.output_dir

        # set default values if needed
        query_window_size = np.round(self.particle_size * 2 / 3)
        query_window_size -= query_window_size % 4
        query_window_size = int(query_window_size)

        self.query_image_size = query_window_size

        if self.max_particle_size is None:
            self.max_particle_size = self.particle_size * 4

        if self.min_particle_size is None:
            self.min_particle_size = int(self.particle_size / 6)

        if self.minimum_overlap_amount is None:
            self.minimum_overlap_amount = int(self.particle_size / 10)
            
        if self.output_dir is None:
            path = os.path.dirname(mrc_dir)
            abs_path = os.path.abspath(mrc_dir)
            self.output_dir = abs_path.replace(path, 'star_dir')
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)

        qBox = (4000 ** 2) / (self.query_image_size ** 2) * 4
        if self.tau1 is None:
            self.tau1 = int(qBox * 3 / 100)

        if self.tau2 is None:
            self.tau2 = int(qBox * 30 / 100)

        self.verify_input_values()
        
        print(' Parameter Report '.center(os.get_terminal_size().columns, '=') + '\n')
        print('%(parameter)-40s %(value)-10s' %  {"parameter": "particle size", "value": self.particle_size})
        print('%(parameter)-40s %(value)-10s' %  {"parameter": "query image size", "value": self.query_image_size})
        print('%(parameter)-40s %(value)-10s' %  {"parameter": "maximum particle size", "value": self.max_particle_size})
        print('%(parameter)-40s %(value)-10s' %  {"parameter": "minimal particle size", "value": self.min_particle_size})
        print('%(parameter)-40s %(value)-10s' %  {"parameter": "tolerated overlap", "value": self.minimum_overlap_amount})
        print('%(parameter)-40s %(value)-10s' %  {"parameter": "training set size, particle", "value": self.tau1})
        print('%(parameter)-40s %(value)-10s' %  {"parameter": "training set size, noise", "value": self.tau2})
        print('%(parameter)-40s %(value)-10s' %  {"parameter": "container size", "value": self.container_size})
        print('%(parameter)-40s %(value)-10s' %  {"parameter": "processor pool size", "value": self.proc})
        print('%(parameter)-40s %(value)-10s\n' %  {"parameter": "output directory", "value": self.output_dir})
        print(' Parameter Report '.center(os.get_terminal_size().columns, '=') + '\n')

    def verify_input_values(self):
        if not 1 <= self.max_particle_size <= 3000:
            raise ConfigError("Error", "Max particle size must be in range [1, 3000]!")

        if not 1 <= self.query_image_size <= 3000:
            raise ConfigError("Error", "Query image size must be in range [1, 3000]!")

        if not 5 <= self.particle_size < 3000:
            raise ConfigError("Error", "Particle size must be in range [5, 3000]!")

        if not 1 <= self.min_particle_size < 3000:
            raise ConfigError("Error", "Min particle size must be in range [1, 3000]!")

        max_tau1_value = (4000 / self.query_image_size * 2) ** 2
        if not 0 <= self.tau1 <= max_tau1_value:
            raise ConfigError("Error", "\u03C4\u2081 must be a in range [0, {}]!".format(max_tau1_value))

        max_tau2_value = (4000 / self.query_image_size * 2) ** 2
        if not 0 <= self.tau2 <= max_tau2_value:
            raise ConfigError("Error", "\u03C4\u2082 must be in range [0, {}]!".format(max_tau2_value))

        if not 0 <= self.minimum_overlap_amount <= 3000:
            raise ConfigError("Error", "overlap must be in range [0, 3000]!")

        # max container_size condition is (conainter_size_max * 2 + 200 > 4000), which is 1900
        if not self.particle_size <= self.container_size <= 1900:
            raise ConfigError("Error", "Container size must be within range [{}, 1900]!".format(self.particle_size))

        if self.particle_size < self.query_image_size:
            raise ConfigError("Error", "Particle size must exceed query image size! particle size:{}, "
                                       "query image size: {}".format(self.particle_size, self.query_image_size))

        if self.proc < 1:
            raise ConfigError("Error", "Please select at least one processor!")

    def pick_particles(self, mrc_dir):

        # fetch all mrc files from mrc folder
        filenames = [os.path.basename(file) for file in glob.glob('{}/*.mrc'.format(mrc_dir))]
        print("converting {} mrc files..".format(len(filenames)))

        data = list()
        data.append(mrc_dir)
        data.append(self.particle_size)
        data.append(self.max_particle_size)
        data.append(self.min_particle_size)
        data.append(self.query_image_size)
        data.append(self.tau1)
        data.append(self.tau2)
        data.append(self.minimum_overlap_amount)
        data.append(self.container_size)
        data.append(self.output_dir)

        pool = Pool(processes=self.proc)
        partial_func = partial(Apple.process_micrograph, data)
        pool.map(partial_func, filenames)
        pool.terminate()

    def process_micrograph(data, filenames):
        file_basename, file_extension = os.path.splitext(filenames)

        # parse filename and verify extension is ".mrc"
        if file_extension == '.mrc':  # todo use negative condition, use other func

            picker = Picker()

            directory = data[0]
            pSize = data[1]
            maxSize = data[2]
            minSize = data[3]
            qSize = data[4]
            tau1 = data[5]
            tau2 = data[6]
            moa = data[7]
            cSize = data[8]
            directory_out = data[9]

            # add path to filename
            filename = directory + '/' + filenames

            # Initialize parameters for the APPLE picker
            Picker.initializeParameters(picker, pSize, maxSize, minSize, qSize, tau1, tau2, moa, cSize, filename,
                                        directory_out)

            # update user
            print('Processing {}..'.format(os.path.basename(filenames)))

            # return .mrc file as a float64 array
            microImg = Picker.readMRC(picker)  # return a micrograph as an numpy array

            # compute score for query images
            score = Picker.queryScore(picker, microImg)  # compute score using normalized cross-correlations

            while True:
                # train SVM classifier and classify all windows in micrograph
                segmentation = Picker.runSVM(picker, microImg, score)

                # If all windows are classified identically, update tau_1 or tau_2
                if np.array_equal(segmentation, np.ones((segmentation.shape[0], segmentation.shape[1]))):
                    tau2 = tau2 + 500

                elif np.array_equal(segmentation, np.zeros((segmentation.shape[0], segmentation.shape[1]))):
                    tau1 = tau1 + 500

                else:
                    break

            # discard suspected artifacts
            segmentation = Picker.morphologyOps(picker, segmentation)

            # create output star file
            Picker.extractParticles(picker, segmentation)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Apple Picker')
    parser.add_argument("-s", type=int, metavar='my_particle_size', help="size of particle")
    parser.add_argument("-o", type=str, metavar="output dir",
                        help="name of output folder where star file should be saved "
                             "(by default AP saves to input folder and adds 'picked' to original file name.)")

    parser.add_argument("mrcdir", metavar='input dir', type=str,
                        help="path to folder containing all mrc files to pick.")

    args = parser.parse_args()

    if args.s:
        ApplePickerConfig.particle_size = args.s

    if ApplePickerConfig.particle_size is None:
        raise Exception("particle size is not defined! either set it with -s or adjust config.py")

    if args.o:
        if not os.path.exists(args.o):
            raise ConfigError("Output directory doesn't exist! {}".format(args.o))
        ApplePickerConfig.output_dir = args.o

    apple = Apple(ApplePickerConfig, args.mrcdir)
    apple.pick_particles(args.mrcdir)
